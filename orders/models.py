import uuid

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Order(models.Model):
    """A customer order for one or more tickets.

    Orders are created during checkout and transition through payment
    states. The order total is calculated server-side from line items
    and never trusted from the client.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=32, unique=True, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        help_text="Customer who placed the order (may be a guest account)",
    )
    event = models.ForeignKey(
        "ticketing.Event",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    subtotal_minor = models.PositiveIntegerField(
        default=0,
        help_text="Sum of line item amounts in minor currency units",
    )
    fee_minor = models.PositiveIntegerField(
        default=0,
        help_text="Platform/service fee in minor currency units",
    )
    total_minor = models.PositiveIntegerField(
        default=0,
        help_text="Grand total payable in minor currency units",
    )
    currency = models.CharField(max_length=3, default="LSL")
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        help_text="Client-provided key to prevent duplicate orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("idempotency_key",),
                name="unique_idempotency_key",
                condition=models.Q(idempotency_key__isnull=False)
                & ~models.Q(idempotency_key=""),
            ),
        ]

    def __str__(self):
        return f"{self.reference} — {self.event.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    def _generate_reference(self):
        import secrets

        return "ORD" + secrets.token_hex(8).upper()

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def is_expired(self):
        return self.status == self.Status.EXPIRED

    def mark_paid(self):
        """Mark the order as paid and set the paid timestamp."""
        if self.status != self.Status.PENDING:
            return False
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])
        return True


class OrderLine(models.Model):
    """A single line item within an order.

    Represents either a General Admission ticket category quantity
    or a specific reserved seat.
    """

    class LineType(models.TextChoices):
        TICKET_CATEGORY = "ticket_category", "Ticket category"
        SEAT = "seat", "Reserved seat"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="lines"
    )
    line_type = models.CharField(max_length=20, choices=LineType.choices)
    ticket_category = models.ForeignKey(
        "ticketing.TicketCategory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order_lines",
    )
    seat = models.ForeignKey(
        "seating.Seat",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order_lines",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price_minor = models.PositiveIntegerField(
        help_text="Unit price in minor currency units"
    )
    line_total_minor = models.PositiveIntegerField(
        help_text="Line total in minor currency units"
    )

    class Meta:
        ordering = ["-order__created_at"]

    def __str__(self):
        if self.line_type == self.LineType.TICKET_CATEGORY:
            return f"{self.ticket_category.name} x{self.quantity}"
        return f"Seat {self.seat.label}"

    def save(self, *args, **kwargs):
        self.line_total_minor = self.unit_price_minor * self.quantity
        super().save(*args, **kwargs)


class InventoryHold(models.Model):
    """Short-lived hold for general-admission inventory during checkout."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        RELEASED = "released", "Released"
        CONVERTED = "converted", "Converted to tickets"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="inventory_holds")
    ticket_category = models.ForeignKey("ticketing.TicketCategory", on_delete=models.PROTECT, related_name="inventory_holds")
    quantity = models.PositiveIntegerField()
    session_key = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("ticket_category", "status", "expires_at")),
        ]
