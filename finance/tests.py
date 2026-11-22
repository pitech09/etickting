from django.test import TestCase

from accounts.models import User
from organisations.models import Organisation

from .models import LedgerEntry
from .services import record_balanced_transaction


class FinanceTests(TestCase):
    def test_balanced_transaction_is_idempotent(self):
        organisation = Organisation.objects.create(name="Finance Org", slug="finance-org")
        first = record_balanced_transaction(organisation=organisation, reference="TX-1", description="Ticket sale", idempotency_key="payment-1", debit_account="cash", credit_account="ticket-sales", amount_minor=1000)
        second = record_balanced_transaction(organisation=organisation, reference="TX-2", description="Duplicate", idempotency_key="payment-1", debit_account="cash", credit_account="ticket-sales", amount_minor=1000)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(LedgerEntry.objects.filter(transaction=first).count(), 2)
