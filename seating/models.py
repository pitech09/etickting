import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class SeatingSection(models.Model):
    """A section within a venue (e.g. Stalls, Balcony, VIP).

    Sections are part of a venue's physical layout and are reusable
    across multiple events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(
        "venues.Venue",
        on_delete=models.CASCADE,
        related_name="sections",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default="#6c757d", help_text="Hex color for seating map")
    price_modifier_minor = models.IntegerField(
        default=0,
        help_text="Additional charge in minor currency units for this section",
    )
    is_accessible = models.BooleanField(
        default=False, help_text="Wheelchair-accessible section"
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("venue", "name"),
                name="unique_section_name_per_venue",
            ),
        ]

    def __str__(self):
        return f"{self.venue.name} — {self.name}"


class SeatingRow(models.Model):
    """A row within a seating section (e.g. A, B, C or 1, 2, 3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        SeatingSection, on_delete=models.CASCADE, related_name="rows"
    )
    name = models.CharField(max_length=10, help_text="Row label, e.g. A or 1")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("section", "name"),
                name="unique_row_name_per_section",
            ),
        ]

    def __str__(self):
        return f"{self.section} — Row {self.name}"


class Seat(models.Model):
    """An individual seat within a row.

    The physical seat status (available/blocked/unavailable) is set by
    the venue manager. Event-specific availability (sold, reserved) is
    tracked through SeatReservation and SeatAllocation.
    """

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        BLOCKED = "blocked", "Blocked"
        UNAVAILABLE = "unavailable", "Unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    row = models.ForeignKey(SeatingRow, on_delete=models.CASCADE, related_name="seats")
    number = models.CharField(max_length=10, help_text="Seat number, e.g. 1 or 101")
    label = models.CharField(
        max_length=20,
        help_text="Display label, e.g. A-1 or Balcony 101",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE
    )
    is_accessible = models.BooleanField(
        default=False, help_text="Wheelchair-accessible seat"
    )
    is_restricted_view = models.BooleanField(
        default=False, help_text="Restricted-view seat"
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "number")
        constraints = [
            models.UniqueConstraint(
                fields=("row", "number"),
                name="unique_seat_number_per_row",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def is_currently_available(self):
        """A seat is available if it is not blocked/unavailable and has
        no active reservation or allocation."""
        if self.status != self.Status.AVAILABLE:
            return False
        if self.reservations.filter(status=SeatReservation.Status.ACTIVE).exists():
            return False
        if hasattr(self, "allocation"):
            return False
        return True


class EventSeating(models.Model):
    """Links an event to a venue's seating layout.

    An event with reserved seating references one EventSeating record
    which points to a venue. The sections, rows and seats come from that
    venue. Event-specific pricing and blocking can be layered on top.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(
        "ticketing.Event",
        on_delete=models.CASCADE,
        related_name="event_seating",
    )
    venue = models.ForeignKey(
        "venues.Venue",
        on_delete=models.CASCADE,
        related_name="event_seatings",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("event",),
                name="unique_event_seating",
            ),
        ]

    def __str__(self):
        return f"Seating for {self.event.name} at {self.venue.name}"

    @property
    def total_seats(self):
        return Seat.objects.filter(
            row__section__venue=self.venue, row__section__is_active=True
        ).count()


class SeatReservation(models.Model):
    """Temporary reservation of a seat during checkout.

    Reservations expire after a configurable period (default 10 minutes)
    and are automatically released. Only one active reservation per seat
    is enforced at the database level.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CONVERTED = "converted", "Converted to ticket"
        RELEASED = "released", "Released"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        "ticketing.Event",
        on_delete=models.CASCADE,
        related_name="seat_reservations",
    )
    seat = models.ForeignKey(
        Seat, on_delete=models.CASCADE, related_name="reservations"
    )
    session_key = models.CharField(
        max_length=200,
        help_text="Identifies the checkout session that holds this reservation",
    )
    expires_at = models.DateTimeField(
        help_text="When this reservation expires and the seat is released"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("seat",),
                condition=Q(status="active"),
                name="unique_active_reservation_per_seat",
            ),
        ]

    def __str__(self):
        return f"Reservation for {self.seat.label} ({self.session_key})"

    @property
    def is_expired(self):
        from django.utils import timezone

        return self.status == self.Status.ACTIVE and self.expires_at < timezone.now()


class SeatAllocation(models.Model):
    """Final allocation of a seat to a ticket.

    Created when payment is verified and a reserved-seat ticket is
    issued. One seat can have only one allocation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seat = models.OneToOneField(
        Seat, on_delete=models.PROTECT, related_name="allocation"
    )
    ticket = models.OneToOneField(
        "ticketing.Ticket",
        on_delete=models.PROTECT,
        related_name="seat_allocation",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.seat.label} → {self.ticket.reference}"