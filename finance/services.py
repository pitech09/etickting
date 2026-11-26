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


def organisation_earnings(*, organisation):
    """Return legacy and commission-based revenue without rewriting history."""
    from orders.models import Order

    sales = Order.objects.filter(
        event__organisation=organisation,
        status__in=[Order.Status.PAID, Order.Status.REFUNDED],
    )
    legacy_sales = sales.filter(commission_rate__isnull=True).aggregate(revenue=Sum("total_minor"), fees=Sum("fee_minor"))
    commission_sales = sales.filter(commission_rate__isnull=False).aggregate(
        revenue=Sum("subtotal_minor"), commission=Sum("commission_minor"), provider_cost=Sum("provider_cost_minor")
    )
    refunds = Order.objects.filter(
        event__organisation=organisation, status=Order.Status.REFUNDED
    ).aggregate(total=Sum("total_minor"))["total"] or 0
    paid_payouts = Payout.objects.filter(
        organisation=organisation, status=Payout.Status.PAID
    ).aggregate(total=Sum("amount_minor"))["total"] or 0
    revenue = (legacy_sales["revenue"] or 0) + (commission_sales["revenue"] or 0)
    fees = legacy_sales["fees"] or 0
    commissions = commission_sales["commission"] or 0
    provider_costs = commission_sales["provider_cost"] or 0
    net_revenue = max(Decimal("0.00"), revenue - refunds)
    organiser_net = max(Decimal("0.00"), revenue - refunds - fees - commissions - provider_costs)
    return {
        "revenue_minor": revenue,
        "refunds_minor": refunds,
        "net_revenue_minor": net_revenue,
        "platform_fees_minor": fees,
        "platform_commission_minor": commissions,
        "provider_costs_minor": provider_costs,
        "organiser_gross_minor": max(0, net_revenue - fees),
        "organiser_net_minor": organiser_net,
        "paid_payouts_minor": paid_payouts,
        "payable_minor": max(0, organiser_net - paid_payouts),
        "revenue_maloti": revenue,
        "refunds_maloti": refunds,
        "platform_fees_maloti": fees,
        "platform_commission_maloti": commissions,
        "provider_costs_maloti": provider_costs,
        "organiser_net_maloti": organiser_net,
        "paid_payouts_maloti": paid_payouts,
        "payable_maloti": max(Decimal("0.00"), net_revenue - fees - paid_payouts),
    }


@transaction.atomic
def create_payout(*, organisation, amount_minor, idempotency_key):
    """Create a pending payout; settlement is explicit and provider-backed later."""
    existing = Payout.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing
    amount_minor = Decimal(str(amount_minor))
    if amount_minor <= 0:
        raise ValueError("Payout amount must be positive")
    available = organisation_earnings(organisation=organisation)["payable_minor"]
    if amount_minor > available:
        raise ValueError("Payout exceeds the organisation's payable balance")
    return Payout.objects.create(
        organisation=organisation,
        amount_minor=amount_minor,
        idempotency_key=idempotency_key,
    )


@transaction.atomic
def settle_payout(*, payout_id, provider_reference):
    payout = Payout.objects.select_for_update().get(pk=payout_id)
    if payout.status == Payout.Status.PAID:
        if payout.provider_reference != provider_reference:
            raise ValueError("Payout provider reference does not match the settled payout")
        return payout
    if payout.status != Payout.Status.PENDING:
        raise ValueError("Only pending payouts can be settled")
    if not provider_reference:
        raise ValueError("A provider reference is required to settle a payout")
    payout.status = Payout.Status.PAID
    payout.provider_reference = provider_reference
    payout.paid_at = timezone.now()
    payout.save(update_fields=["status", "provider_reference", "paid_at", "updated_at"])
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
