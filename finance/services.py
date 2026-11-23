import uuid
from decimal import Decimal

from django.db.models import Sum
from django.db import transaction
from django.utils import timezone

from .models import FinancialTransaction, LedgerEntry, Payout


def organisation_earnings(*, organisation):
    """Return paid revenue, fees, paid payouts and the remaining payable amount."""
    from orders.models import Order

    sales = Order.objects.filter(
        event__organisation=organisation,
        status__in=[Order.Status.PAID, Order.Status.REFUNDED],
    ).aggregate(revenue=Sum("total_minor"), fees=Sum("fee_minor"))
    refunds = Order.objects.filter(
        event__organisation=organisation, status=Order.Status.REFUNDED
    ).aggregate(total=Sum("total_minor"))["total"] or 0
    paid_payouts = Payout.objects.filter(
        organisation=organisation, status=Payout.Status.PAID
    ).aggregate(total=Sum("amount_minor"))["total"] or 0
    revenue = sales["revenue"] or 0
    fees = sales["fees"] or 0
    net_revenue = max(0, revenue - refunds)
    return {
        "revenue_minor": revenue,
        "refunds_minor": refunds,
        "net_revenue_minor": net_revenue,
        "platform_fees_minor": fees,
        "organiser_gross_minor": max(0, net_revenue - fees),
        "paid_payouts_minor": paid_payouts,
        "payable_minor": max(0, net_revenue - fees - paid_payouts),
        "revenue_maloti": Decimal(revenue) / Decimal("100"),
        "refunds_maloti": Decimal(refunds) / Decimal("100"),
        "platform_fees_maloti": Decimal(fees) / Decimal("100"),
        "paid_payouts_maloti": Decimal(paid_payouts) / Decimal("100"),
        "payable_maloti": Decimal(max(0, net_revenue - fees - paid_payouts)) / Decimal("100"),
    }


@transaction.atomic
def create_payout(*, organisation, amount_minor, idempotency_key):
    """Create a pending payout; settlement is explicit and provider-backed later."""
    existing = Payout.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing
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
    if amount_minor <= 0:
        raise ValueError("Ledger amount must be positive")
    record, created = FinancialTransaction.objects.get_or_create(organisation=organisation, idempotency_key=idempotency_key, defaults={"reference": reference or f"TX-{uuid.uuid4().hex[:12].upper()}", "description": description})
    if not created:
        return record
    LedgerEntry.objects.create(transaction=record, account=debit_account, debit_minor=amount_minor)
    LedgerEntry.objects.create(transaction=record, account=credit_account, credit_minor=amount_minor)
    return record
