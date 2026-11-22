import uuid

from django.db import transaction

from .models import FinancialTransaction, LedgerEntry


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
