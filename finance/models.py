import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class FinancialTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey("organisations.Organisation", on_delete=models.PROTECT, related_name="financial_transactions")
    reference = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LedgerEntry(models.Model):
    transaction = models.ForeignKey(FinancialTransaction, on_delete=models.PROTECT, related_name="entries")
    account = models.CharField(max_length=100)
    debit_minor = models.PositiveIntegerField(default=0)
    credit_minor = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if (self.debit_minor > 0) == (self.credit_minor > 0):
            raise ValidationError("A ledger entry must contain either a debit or a credit.")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(debit_minor__gt=0) | models.Q(credit_minor__gt=0), name="ledger_entry_has_amount")]


class Payout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    organisation = models.ForeignKey("organisations.Organisation", on_delete=models.PROTECT, related_name="payouts")
    amount_minor = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
