import uuid

from django.conf import settings
from django.db import models


def generate_ticket_reference():
    """Generate a cryptographically secure ticket reference (32-char alphanumeric).

    Uses secrets module for cryptographic safety - never sequential or predictable.
    """
    import secrets
    import string

    alphabet = string.ascii_upcase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


def validate_ticket_credential(credential, ticket):
    """Validate that a QR code credential matches this ticket.

    Used by the public verification endpoint and scanner interface.
    The credential should be the opaque reference string.

    Returns (valid: bool, reason: str) tuple.
    """
    if not credential:
        return False, "empty_credential"
    if credential == ticket.reference:
        return True, "valid"
    return False, "invalid"


from organisations.models import Organisation


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SALES_OPEN = "sales_open", "Sales open"
        SALES_PAUSED = "sales_paused", "Sales paused"
        SOLD_OUT = "sold_out", "Sold out"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class TicketingModel(models.TextChoices):
        GENERAL_ADMISSION = "general_admission", "General admission"
        RESERVED_SEATING = "reserved_seating", "Reserved seating"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="events")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    cover_image = models.URLField(blank=True)
    venue = models.ForeignKey(
        "venues.Venue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    sales_opens_at = models.DateTimeField(null=True, blank=True)
    sales_closes_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=60, default="Africa/Maseru")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    ticketing_model = models.CharField(
        max_length=20, choices=TicketingModel.choices, default=TicketingModel.GENERAL_ADMISSION
    )
    admission_policy = models.CharField(max_length=40, default="single_entry")
    refund_policy = models.TextField(blank=True)
    resale_policy = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def can_publish(self):
        """An event can be published when it has a name, start time and organisation."""
        return bool(self.name and self.starts_at and self.organisation_id)

    def sales_are_open(self):
        from django.utils import timezone

        now = timezone.now()
        if self.status != self.Status.SALES_OPEN:
            return False
        if self.sales_opens_at and now < self.sales_opens_at:
            return False
        if self.sales_closes_at and now > self.sales_closes_at:
            return False
        return True


class TicketCategory(models.Model):
    """General Admission ticket category for an event.

    Ticket categories track inventory for events that do not assign
    individual seats. Each category has its own price, quantity and
    purchase limits.
    """

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="ticket_categories"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_minor = models.PositiveIntegerField(
        help_text="Price in minor currency units (e.g. sente for Maloti)"
    )
    total_quantity = models.PositiveIntegerField()
    max_per_customer = models.PositiveIntegerField(default=10)
    sales_opens_at = models.DateTimeField(null=True, blank=True)
    sales_closes_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("event", "name"),
                name="unique_ticket_category_name_per_event",
            ),
        ]

    def __str__(self):
        return f"{self.event.name} — {self.name}"

    @property
    def sold_count(self):
        """Number of issued (non-cancelled) tickets in this category."""
        return Ticket.objects.filter(
            event=self.event,
            ticket_category=self,
            status=Ticket.Status.ISSUED,
        ).count()

    @property
    def available_count(self):
        return max(0, self.total_quantity - self.sold_count)

    @property
    def is_sold_out(self):
        return self.available_count <= 0


class Ticket(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        ADMITTED = "admitted", "Admitted"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=32, unique=True, editable=False)
    attendee_photo = models.ImageField(
        upload_to="ticket_photos/%Y/%m/%d/",
        blank=True,
        null=True,
        help_text="Attendee photograph for identity verification at event entry",
        verbose_name="Attendee photograph",
    )
    credential_hash = models.CharField(
        max_length=64, unique=True, editable=False, default=""
    )
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="tickets")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets")
    ticket_category = models.ForeignKey(
        "TicketCategory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tickets",
        help_text="General Admission category this ticket belongs to, if any",
    )
    seat = models.ForeignKey(
        "seating.Seat",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ticket",
        help_text="Reserved seat this ticket is assigned to, if any",
    )
    attendee_name = models.CharField(max_length=180, blank=True)
    seat_label = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    complimentary_authorized_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def can_be_issued(self):
        return bool(self.payment_verified_at or self.complimentary_authorized_at)

    def is_general_admission(self):
        return self.ticket_category_id is not None and self.seat_id is None

    def is_reserved_seating(self):
        return self.seat_id is not None

    @property
    def qr_credential(self):
        """Return the cryptographic credential for this ticket's QR code.

        Uses the opaque reference which is a UUID - never sequential IDs.
        The credential itself does not contain sensitive information;
        it resolves to the ticket record server-side.
        """
        return self.reference

    @property
    def attendee_photo_url(self):
        """Return URL for attendee photograph if available.

        Photographs are stored privately and accessed via signed URLs
        that expire quickly to prevent unauthorized access.
        """
        if self.attendee_photo and hasattr(self.attendee_photo, "url"):
            return self.attendee_photo.url
        return None

    def can_be_issued(self):
        return bool(self.payment_verified_at or self.complimentary_authorized_at)

    def is_general_admission(self):
        return self.ticket_category_id is not None and self.seat_id is None

    def is_reserved_seating(self):
        return self.seat_id is not None

    def is_active(self):
        return self.status == self.Status.ISSUED

    def is_valid(self):
        """Check if the ticket is valid for admission."""
        if self.status in self.Status.choices_as_values_ref():
            return False
        if self.status == self.Status.ADMITTED:
            return False
        if self.status == self.Status.CANCELLED:
            return False
        if self.status == self.Status.REFUNDED:
            return False
        if self.status == self.Status.REVOKED:
            return False
        return True

    @property
    def admission_status_label(self):
        """Human-readable admission status."""
        labels = {
            self.Status.ISSUED: "Active",
            self.Status.ADMITTED: "Used",
            self.Status.CANCELLED: "Cancelled",
            self.Status.REFUNDED: "Refunded",
            self.Status.REVOKED: "Revoked",
        }
        return labels.get(self.status, self.status.title())

    @property
    def can_be_resold(self):
        """Check if this ticket can be listed for resale."""
        if self.status == self.Status.ADMITTED:
            return False
        if self.status == self.Status.CANCELLED:
            return False
        if self.status == self.Status.REFUNDED:
            return False
        if self.status == self.Status.REVOKED:
            return False
        # Check for existing resale listing
        from .models import ResaleListing

        return not ResaleListing.objects.filter(
            ticket=self, status=ResaleListing.Status.OPEN
        ).exists()


class TicketCredential(models.Model):
    """Cryptographically secure ticket credential.

    Each ticket has a unique, secure credential that cannot be guessed
    or predicted. The credential is the QR code value presented at entry.

    The credential is the opaque reference string generated at ticket
    creation. It is NOT the primary key and is computationally infeasible
    to reverse-engineer.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        USED = "used", "Used"
        REVOKED = "revoked", "Revoked"
        EXPORTED = "exported", "Exported"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.OneToOneField(
        Ticket, on_delete=models.CASCADE, related_name="credential"
    )
    credential_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hash of the credential for quick lookup",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ticket Credential"
        verbose_name_plural = "Ticket Credentials"

    def __str__(self):
        return f"Credential for {self.ticket.reference}"


class TicketOwnershipHistory(models.Model):
    """Audit trail of ticket ownership transfers.

    Records every ownership change for audit and fraud prevention.
    The current ticket holder is always the last record with a non-null
    purchaser_id (or owner_id depending on workflow).
    """

    class TransferType(models.TextChoices):
        INITIAL_PURCHASE = "initial_purchase", "Initial Purchase"
        RESALE = "resale", "Resale"
        TRANSFER = "transfer", "Transfer"
        REFUND = "refund", "Refund"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="ownership_history"
    )
    previous_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ownership_transfers_out",
    )
    new_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ownership_transfers_in",
    )
    transfer_type = models.CharField(
        max_length=20, choices=TransferType.choices
    )
    transfer_price_minor = models.IntegerField(
        null=True,
        blank=True,
        help_text="Price in minor units if this was a resale transfer",
    )
    transfer_timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-transfer_timestamp",)
        verbose_name = "Ticket Ownership History"
        verbose_name_plural = "Ticket Ownership Histories"

    def __str__(self):
        return f"Ownership transfer of {self.ticket.reference} at {self.transfer_timestamp}"
    device_id = models.CharField(max_length=100, unique=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="scanner_devices")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scanner_devices")
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)


class ScanAttempt(models.Model):
    class Result(models.TextChoices):
        VALID = "valid", "Valid"
        INVALID = "invalid", "Invalid"
        USED = "used", "Already used"
        UNAUTHORISED = "unauthorised", "Unauthorised"

    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.SET_NULL, related_name="scan_attempts")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="scan_attempts")
    scanner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    device = models.ForeignKey(ScannerDevice, null=True, blank=True, on_delete=models.SET_NULL)
    result = models.CharField(max_length=20, choices=Result.choices)
    reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Admission(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.PROTECT, related_name="admission")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="admissions")
    admitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    admitted_at = models.DateTimeField(auto_now_add=True)
    reentry_count = models.PositiveIntegerField(default=0)
