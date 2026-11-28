import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PlatformCommissionConfig(models.Model):
    """Current platform commission setting; historical sales snapshot the rate."""

    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


class CommissionTransaction(models.Model):
    """Immutable commission snapshot for one successful ticket sale."""

    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="commission_transaction")
    payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT, related_name="commission_transaction")
    organisation = models.ForeignKey("organisations.Organisation", on_delete=models.PROTECT, related_name="commission_transactions")
    event = models.ForeignKey("ticketing.Event", on_delete=models.PROTECT, related_name="commission_transactions")
    gross_ticket_sales_minor = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    commission_minor = models.DecimalField(max_digits=12, decimal_places=2)
    provider_cost_minor = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    organiser_net_minor = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if self.pk and CommissionTransaction.objects.filter(pk=self.pk).exists():
            raise ValidationError("Commission transactions are immutable")
        super().save(*args, **kwargs)


class RefundCommissionAdjustment(models.Model):
    """Immutable reversal of a historical commission after a completed refund."""

    refund = models.OneToOneField("payments.RefundRequest", on_delete=models.PROTECT, related_name="commission_adjustment")
    commission_transaction = models.ForeignKey(CommissionTransaction, on_delete=models.PROTECT, related_name="refund_adjustments")
    eligible_sales_refunded_minor = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    commission_reversal_minor = models.DecimalField(max_digits=12, decimal_places=2)
    organiser_recovery_minor = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if self.pk and RefundCommissionAdjustment.objects.filter(pk=self.pk).exists():
            raise ValidationError("Refund commission adjustments are immutable")
        super().save(*args, **kwargs)


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
    debit_minor = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    credit_minor = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if (self.debit_minor > 0) == (self.credit_minor > 0):
            raise ValidationError("A ledger entry must contain either a debit or a credit.")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(debit_minor__gt=0) | models.Q(credit_minor__gt=0), name="ledger_entry_has_amount")]


class Payout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        INITIATED = "initiated", "Initiated"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    organisation = models.ForeignKey("organisations.Organisation", on_delete=models.PROTECT, related_name="payouts")
    event = models.ForeignKey(
        "ticketing.Event",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payouts",
        help_text="Optional event that prompted this settlement request.",
    )
    payment_method = models.ForeignKey("organisations.OrganisationPaymentMethod", null=True, blank=True, on_delete=models.SET_NULL, related_name="payouts")
    amount_minor = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="LSL")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=160, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    failure_reason = models.TextField(blank=True)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="initiated_payouts")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="requested_payouts")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="confirmed_payouts")
    initiation_note = models.TextField(blank=True)
    request_note = models.TextField(blank=True)
    confirmation_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    initiated_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    @property
    def amount_maloti(self):
        return self.amount_minor
