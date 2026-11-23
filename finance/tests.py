from django.test import TestCase

from accounts.models import User
from organisations.models import Organisation
from orders.models import Order
from django.utils import timezone

from .models import LedgerEntry, Payout
from .services import create_payout, organisation_earnings, record_balanced_transaction, settle_payout


class FinanceTests(TestCase):
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
