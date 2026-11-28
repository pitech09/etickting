import uuid
from decimal import Decimal
from decimal import ROUND_HALF_UP

from django.db.models import Sum
from django.db import transaction
from django.utils import timezone

from .models import CommissionTransaction, FinancialTransaction, LedgerEntry, Payout, PlatformCommissionConfig


def current_commission_rate():
    return PlatformCommissionConfig.current().commission_rate


def calculate_commission(gross_ticket_sales_minor, commission_rate):
    gross_ticket_sales_minor = Decimal(str(gross_ticket_sales_minor))
    rate = Decimal(commission_rate)
    if rate < Decimal("0") or rate > Decimal("100"):
        raise ValueError("Commission rate must be between 0 and 100 percent")
    return (Decimal(gross_ticket_sales_minor) * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def record_commission_for_payment(*, payment, order):
    if order.commission_rate is None:
        return None
    existing = CommissionTransaction.objects.filter(order=order).first()
    if existing:
        return existing
    subtotal = Decimal(str(order.subtotal_minor))
    provider_cost = Decimal(str(order.provider_cost_minor or "0"))
    commission_minor = calculate_commission(subtotal, order.commission_rate)
    return CommissionTransaction.objects.create(
        order=order,
        payment=payment,
        organisation=order.event.organisation,
        event=order.event,
        gross_ticket_sales_minor=subtotal,
        commission_rate=order.commission_rate,
        commission_minor=commission_minor,
        provider_cost_minor=provider_cost,
        organiser_net_minor=max(Decimal("0.00"), subtotal - commission_minor - provider_cost),
    )


def organisation_earnings(*, organisation, event=None):
    """Return legacy and commission-based revenue without rewriting history."""
    from orders.models import Order

    if event is not None and event.organisation_id != organisation.pk:
        raise ValueError("The event does not belong to this organisation")
    sales = Order.objects.filter(
        event__organisation=organisation,
        status__in=[Order.Status.PAID, Order.Status.REFUNDED],
    )
    if event is not None:
        sales = sales.filter(event=event)
    legacy_sales = sales.filter(commission_rate__isnull=True).aggregate(revenue=Sum("total_minor"), fees=Sum("fee_minor"))
    commission_sales = sales.filter(commission_rate__isnull=False).aggregate(
        revenue=Sum("subtotal_minor"), commission=Sum("commission_minor"), provider_cost=Sum("provider_cost_minor")
    )
    from .models import RefundCommissionAdjustment
    from payments.models import RefundRequest

    refunds = RefundRequest.objects.filter(
        order__event__organisation=organisation,
        status=RefundRequest.Status.COMPLETED,
    )
    if event is not None:
        refunds = refunds.filter(order__event=event)
    refunds = refunds.aggregate(total=Sum("approved_amount_minor"))["total"] or 0
    legacy_refunds = sales.filter(status=Order.Status.REFUNDED).exclude(
        refund_requests__status=RefundRequest.Status.COMPLETED,
    ).aggregate(total=Sum("total_minor"))["total"] or 0
    refunds += legacy_refunds
    paid_payouts_query = Payout.objects.filter(organisation=organisation, status=Payout.Status.PAID)
    if event is not None:
        paid_payouts_query = paid_payouts_query.filter(event=event)
    paid_payouts = paid_payouts_query.aggregate(total=Sum("amount_minor"))["total"] or 0
    revenue = (legacy_sales["revenue"] or 0) + (commission_sales["revenue"] or 0)
    fees = legacy_sales["fees"] or 0
    commissions = commission_sales["commission"] or 0
    commission_reversals_query = RefundCommissionAdjustment.objects.filter(
        refund__order__event__organisation=organisation,
    )
    if event is not None:
        commission_reversals_query = commission_reversals_query.filter(
            commission_transaction__event=event
        )
    commission_reversals = commission_reversals_query.aggregate(
        total=Sum("commission_reversal_minor")
    )["total"] or 0
    provider_costs = commission_sales["provider_cost"] or 0
    net_revenue = max(Decimal("0.00"), revenue - refunds)
    net_commissions = commissions - commission_reversals
    organiser_net = revenue - refunds - fees - net_commissions - provider_costs
    organiser_recovery = max(Decimal("0.00"), paid_payouts - organiser_net)
    return {
        "revenue_minor": revenue,
        "refunds_minor": refunds,
        "net_revenue_minor": net_revenue,
        "platform_fees_minor": fees,
        "platform_commission_minor": net_commissions,
        "commission_reversals_minor": commission_reversals,
        "provider_costs_minor": provider_costs,
        "organiser_gross_minor": max(0, net_revenue - fees),
        "organiser_net_minor": organiser_net,
        "paid_payouts_minor": paid_payouts,
        "payable_minor": max(Decimal("0.00"), organiser_net - paid_payouts),
        "organiser_recovery_minor": organiser_recovery,
        "revenue_maloti": revenue,
        "refunds_maloti": refunds,
        "platform_fees_maloti": fees,
        "platform_commission_maloti": net_commissions,
        "commission_reversals_maloti": commission_reversals,
        "provider_costs_maloti": provider_costs,
        "organiser_net_maloti": organiser_net,
        "paid_payouts_maloti": paid_payouts,
        "payable_maloti": max(Decimal("0.00"), organiser_net - paid_payouts),
        "organiser_recovery_maloti": organiser_recovery,
    }


@transaction.atomic
def record_refund_commission_reversal(*, refund, actor=None):
    """Create one immutable proportional reversal for a completed refund."""
    from .models import RefundCommissionAdjustment

    existing = RefundCommissionAdjustment.objects.filter(refund=refund).first()
    if existing:
        return existing
    try:
        commission = refund.order.commission_transaction
    except CommissionTransaction.DoesNotExist:
        commission = None
    if not commission:
        return None
    from decimal import Decimal

    refunded = Decimal(str(refund.approved_amount_minor or "0.00"))
    eligible = min(refunded, Decimal(str(refund.order.subtotal_minor)))
    reversal = calculate_commission(eligible, commission.commission_rate)
    recovery = refunded - reversal
    return RefundCommissionAdjustment.objects.create(
        refund=refund,
        commission_transaction=commission,
        eligible_sales_refunded_minor=eligible,
        commission_rate=commission.commission_rate,
        commission_reversal_minor=reversal,
        organiser_recovery_minor=recovery,
        recorded_by=actor,
    )


@transaction.atomic
def create_payout(*, organisation, amount_minor, idempotency_key, payment_method=None, event=None, requested_by=None, request_note=""):
    """Create a pending payout; settlement is explicit and provider-backed later."""
    existing = Payout.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing
    amount_minor = Decimal(str(amount_minor))
    if amount_minor <= 0:
        raise ValueError("Payout amount must be positive")
    available = organisation_earnings(organisation=organisation)["payable_minor"]
    reserved = Payout.objects.filter(
        organisation=organisation,
        status__in=[Payout.Status.PENDING, Payout.Status.INITIATED],
    ).aggregate(total=Sum("amount_minor"))["total"] or Decimal("0.00")
    available -= reserved
    if amount_minor > available:
        raise ValueError("Payout exceeds the organisation's payable balance")
    if event is not None and event.organisation_id != organisation.pk:
        raise ValueError("The event does not belong to this organisation")
    if payment_method is not None and payment_method.organisation_id != organisation.pk:
        raise ValueError("Choose a settlement method belonging to this organisation")
    return Payout.objects.create(
        organisation=organisation,
        event=event,
        payment_method=payment_method,
        amount_minor=amount_minor,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
        request_note=str(request_note or "").strip(),
    )


@transaction.atomic
def initiate_payout(*, payout_id, actor=None, note=""):
    payout = Payout.objects.select_for_update().get(pk=payout_id)
    if payout.status != Payout.Status.PENDING:
        raise ValueError("Only pending payouts can be initiated")
    payout.status = Payout.Status.INITIATED
    payout.initiated_by = actor
    payout.initiation_note = str(note or "").strip()
    payout.initiated_at = timezone.now()
    payout.save(update_fields=["status", "initiated_by", "initiation_note", "initiated_at", "updated_at"])
    return payout


@transaction.atomic
def settle_payout(*, payout_id, provider_reference, confirmer=None, note=""):
    payout = Payout.objects.select_for_update().get(pk=payout_id)
    if payout.status == Payout.Status.PAID:
        if payout.provider_reference != provider_reference:
            raise ValueError("Payout provider reference does not match the settled payout")
        return payout
    if payout.status != Payout.Status.INITIATED:
        raise ValueError("Only initiated payouts can be settled")
    if not provider_reference:
        raise ValueError("A provider reference is required to settle a payout")
    payout.status = Payout.Status.PAID
    payout.provider_reference = provider_reference
    payout.confirmed_by = confirmer
    payout.confirmation_note = str(note or "").strip()
    payout.paid_at = timezone.now()
    payout.save(update_fields=["status", "provider_reference", "confirmed_by", "confirmation_note", "paid_at", "updated_at"])
    return payout


@transaction.atomic
def fail_payout(*, payout_id, reason):
    payout = Payout.objects.select_for_update().get(pk=payout_id)
    if payout.status not in {Payout.Status.PENDING, Payout.Status.INITIATED}:
        raise ValueError("Only open payouts can be marked failed")
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("Explain why the payout failed")
    payout.status = Payout.Status.FAILED
    payout.failure_reason = reason
    payout.save(update_fields=["status", "failure_reason", "updated_at"])
    return payout


@transaction.atomic
def record_balanced_transaction(*, organisation, reference, description, idempotency_key, debit_account, credit_account, amount_minor):
    amount_minor = Decimal(str(amount_minor))
    if amount_minor <= 0:
        raise ValueError("Ledger amount must be positive")
    record, created = FinancialTransaction.objects.get_or_create(organisation=organisation, idempotency_key=idempotency_key, defaults={"reference": reference or f"TX-{uuid.uuid4().hex[:12].upper()}", "description": description})
    if not created:
        return record
    LedgerEntry.objects.create(transaction=record, account=debit_account, debit_minor=amount_minor)
    LedgerEntry.objects.create(transaction=record, account=credit_account, credit_minor=amount_minor)
    return record
