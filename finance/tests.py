from decimal import Decimal
from django.test import TestCase

from accounts.models import User
from organisations.models import Organisation
from orders.models import Order
from django.utils import timezone

from payments.models import Payment
from .models import CommissionTransaction, LedgerEntry, Payout, PlatformCommissionConfig
from .services import calculate_commission, create_payout, organisation_earnings, record_balanced_transaction, record_commission_for_payment, settle_payout


class FinanceTests(TestCase):
    def test_commission_uses_decimal_arithmetic(self):
        self.assertEqual(calculate_commission(1000000, "10.00"), 100000)
        self.assertEqual(calculate_commission(10001, "10.00"), 1000)

    def test_commission_rate_changes_do_not_recalculate_existing_order_snapshot(self):
        first = PlatformCommissionConfig.current()
        first.commission_rate = "10.00"
        first.save(update_fields=["commission_rate", "updated_at"])
        organisation = Organisation.objects.create(name="Commission Org", slug="commission-org")
        customer = User.objects.create_user(email="commission-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Commission Event", starts_at=timezone.now())
        first_order = Order.objects.create(
            customer=customer, event=event, status=Order.Status.PAID,
            subtotal_minor=10000, total_minor=10000, commission_rate=first.commission_rate,
            commission_minor=1000, organiser_net_minor=9000,
        )
        first.commission_rate = "12.50"
        first.save(update_fields=["commission_rate", "updated_at"])
        first_order.refresh_from_db()
        self.assertEqual(first_order.commission_rate, Decimal("10.00"))
        self.assertEqual(calculate_commission(10000, first.commission_rate), 1250)

    def test_successful_sale_creates_one_idempotent_commission_snapshot(self):
        organisation = Organisation.objects.create(name="Commission Sales", slug="commission-sales")
        customer = User.objects.create_user(email="sale-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Commission Sale", starts_at=timezone.now())
        order = Order.objects.create(
            customer=customer, event=event, status=Order.Status.PAID,
            subtotal_minor=10000, total_minor=10000, commission_rate="10.00",
            commission_minor=1000, organiser_net_minor=9000,
        )
        payment = Payment.objects.create(
            order=order, provider=Payment.Provider.MPESA,
            status=Payment.Status.SUCCESSFUL, amount_minor=10000,
            provider_reference="COMMISSION-1",
        )
        first = record_commission_for_payment(payment=payment, order=order)
        second = record_commission_for_payment(payment=payment, order=order)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CommissionTransaction.objects.get(pk=first.pk).commission_minor, 1000)

    def test_balanced_transaction_is_idempotent(self):
        organisation = Organisation.objects.create(name="Finance Org", slug="finance-org")
        first = record_balanced_transaction(organisation=organisation, reference="TX-1", description="Ticket sale", idempotency_key="payment-1", debit_account="cash", credit_account="ticket-sales", amount_minor=1000)
        second = record_balanced_transaction(organisation=organisation, reference="TX-2", description="Duplicate", idempotency_key="payment-1", debit_account="cash", credit_account="ticket-sales", amount_minor=1000)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(LedgerEntry.objects.filter(transaction=first).count(), 2)

    def test_earnings_include_refunds_and_payout_balance(self):
        organisation = Organisation.objects.create(name="Settlement Org", slug="settlement-org")
        customer = User.objects.create_user(email="finance-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Finance Event", starts_at=timezone.now())
        Order.objects.create(customer=customer, event=event, status=Order.Status.PAID, total_minor=10000, fee_minor=500)
        Order.objects.create(customer=customer, event=event, status=Order.Status.REFUNDED, total_minor=2000, fee_minor=100)
        self.assertEqual(organisation_earnings(organisation=organisation)["payable_minor"], 9400)
        payout = create_payout(organisation=organisation, amount_minor=9400, idempotency_key="settlement-1")
        self.assertEqual(Payout.objects.count(), 1)
        settle_payout(payout_id=payout.pk, provider_reference="BANK-1")
        self.assertEqual(organisation_earnings(organisation=organisation)["payable_minor"], 0)
