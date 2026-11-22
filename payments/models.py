import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """A payment linked to an order, processed by a payment provider.

    Payment status is established only by server-side provider
    confirmation — never by the browser.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        INITIATED = "initiated", "Initiated"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        REVERSED = "reversed", "Reversed"
        REFUNDED = "refunded", "Refunded"

    class Provider(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        ECOCASH = "ecocash", "EcoCash"
        SANDBOX = "sandbox", "Sandbox (development)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    amount_minor = models.PositiveIntegerField(
        help_text="Amount payable in minor currency units"
    )
    currency = models.CharField(max_length=3, default="LSL")
    provider_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text="Transaction reference from the payment provider",
    )
    provider_response = models.JSONField(
        default=dict, blank=True, help_text="Raw provider response for audit"
    )
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        help_text="Key to prevent duplicate payment processing",
    )
    callback_processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("idempotency_key",),
                name="unique_payment_idempotency_key",
                condition=models.Q(idempotency_key__isnull=False)
                & ~models.Q(idempotency_key=""),
            ),
        ]

    def __str__(self):
        return f"{self.reference_short} — {self.get_status_display()}"

    @property
    def reference_short(self):
        return str(self.id)[:8].upper()

    @property
    def is_successful(self):
        return self.status == self.Status.SUCCESSFUL

    def mark_successful(self, provider_reference=None, response=None):
        """Mark payment successful — only called from verified provider callbacks."""
        if self.status != self.Status.PENDING and self.status != self.Status.INITIATED:
            return False
        self.status = self.Status.SUCCESSFUL
        if provider_reference:
            self.provider_reference = provider_reference
        if response is not None:
            self.provider_response = response or {}
        self.callback_processed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "provider_reference",
                "provider_response",
                "callback_processed_at",
                "updated_at",
            ]
        )
        return True

    def mark_failed(self, reason=None, response=None):
        if self.status != self.Status.PENDING and self.status != self.Status.INITIATED:
            return False
        self.status = self.Status.FAILED
        if response is not None:
            self.provider_response = response or {}
        if reason:
            self.provider_response = {**self.provider_response, "failure_reason": reason}
        self.callback_processed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "provider_response",
                "callback_processed_at",
                "updated_at",
            ]
        )
        return True


class PaymentProviderRegistry:
    """Simple registry of available payment providers.

    Providers are looked up by name. The registry is intentionally
    lightweight — providers are plain Python classes, not Django models.
    """

    _providers = {}

    @classmethod
    def register(cls, name, provider_cls):
        cls._providers[name] = provider_cls

    @classmethod
    def get(cls, name):
        return cls._providers.get(name)

    @classmethod
    def all(cls):
        return list(cls._providers.keys())