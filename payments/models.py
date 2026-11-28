import uuid
from decimal import Decimal

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
        BANK = "bank", "Bank transfer"
        OTHER = "other", "Other"
        SANDBOX = "sandbox", "Sandbox (development)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_method = models.ForeignKey(
        "organisations.OrganisationPaymentMethod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    amount_minor = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount payable in Maloti")
    currency = models.CharField(max_length=3, default="LSL")
    provider_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text="Transaction reference from the payment provider",
    )
    sender_phone = models.CharField(
        max_length=40,
        blank=True,
        help_text="Customer mobile number used to make a manual payment",
    )
    received_amount_minor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount confirmed against the mobile money transaction by a reviewer in Maloti",
    )
    proof_image = models.ImageField(
        upload_to="payment-proofs/%Y/%m/",
        blank=True,
        null=True,
        help_text="Customer payment screenshot for manual review",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_payments",
    )
    review_note = models.TextField(blank=True)
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
            models.UniqueConstraint(
                fields=("provider", "provider_reference"),
                name="unique_provider_transaction_reference",
                condition=models.Q(provider_reference__isnull=False)
                & ~models.Q(provider_reference=""),
            ),
        ]

    def __str__(self):
        return f"{self.reference_short} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if self.provider_reference:
            self.provider_reference = self.provider_reference.strip().upper()
        super().save(*args, **kwargs)

    @property
    def reference_short(self):
        return str(self.id)[:8].upper()

    @property
    def is_successful(self):
        return self.status == self.Status.SUCCESSFUL

    def mark_successful(self, provider_reference=None, response=None, received_amount_minor=None):
        """Mark payment successful — only called from verified provider callbacks."""
        if self.status != self.Status.PENDING and self.status != self.Status.INITIATED:
            return False
        self.status = self.Status.SUCCESSFUL
        if provider_reference:
            self.provider_reference = provider_reference
        if response is not None:
            self.provider_response = response or {}
        if received_amount_minor is not None:
            self.received_amount_minor = received_amount_minor
        self.callback_processed_at = timezone.now()
        update_fields = ["status", "provider_reference", "provider_response", "callback_processed_at", "updated_at"]
        if received_amount_minor is not None:
            update_fields.append("received_amount_minor")
        self.save(update_fields=update_fields)
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


class PaymentReview(models.Model):
    """Append-only record of every manual payment decision."""

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="review_history")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    previous_status = models.CharField(max_length=20)
    resulting_status = models.CharField(max_length=20)
    received_amount_minor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class RefundRequest(models.Model):
    """An auditable customer refund entitlement and execution record."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed / intervention required"

    class NotificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="refund_requests")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refund_requests")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="refund_requests")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_refunds")
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="executed_refunds")
    requested_amount_minor = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount_minor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.REQUESTED)
    reason = models.TextField()
    review_note = models.TextField(blank=True)
    execution_note = models.TextField(blank=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    is_event_cancellation = models.BooleanField(default=False)
    notification_status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    notification_error = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-requested_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(requested_amount_minor__gt=0),
                name="refund_request_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(approved_amount_minor__isnull=True) | models.Q(approved_amount_minor__gt=0),
                name="refund_approved_amount_positive",
            ),
            models.UniqueConstraint(
                fields=("order", "is_event_cancellation"),
                condition=models.Q(is_event_cancellation=True),
                name="one_event_cancellation_refund_per_order",
            ),
        ]

    @property
    def approved_amount_maloti(self):
        return self.approved_amount_minor or 0
