from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import EventSeating, Seat, SeatAllocation, SeatReservation


def calculate_seat_price(*, category, seat):
    """Calculate a reserved seat's configured price in Maloti."""
    try:
        configured_section_price = seat.row.section.ticket_price_minor
        base_price = Decimal(str(
            configured_section_price if configured_section_price is not None else category.price_minor
        ))
        supplement = Decimal(str(seat.row.section.price_modifier_minor or "0.00"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("This ticket has an invalid price configuration.") from exc
    if base_price < 0 or supplement < 0:
        raise ValueError("This ticket has an invalid price configuration.")
    return (base_price + supplement).quantize(Decimal("0.01"))


def get_customer_seat_map_data(event):
    """Return the server-authoritative seat state used by customer checkout."""
    try:
        event_seating = event.event_seating
    except EventSeating.DoesNotExist:
        return []

    from .models import SeatingSection

    sections = (
        SeatingSection.objects.filter(venue=event_seating.venue)
        .prefetch_related("rows__seats")
        .order_by("sort_order", "name")
    )
    seats = [seat for section in sections for row in section.rows.all() for seat in row.seats.all()]
    seat_ids = [seat.id for seat in seats]
    allocated_seat_ids = set(
        SeatAllocation.objects.filter(seat_id__in=seat_ids).values_list("seat_id", flat=True)
    )
    active_reservations = {
        reservation.seat_id: reservation
        for reservation in SeatReservation.objects.filter(
            event=event,
            seat_id__in=seat_ids,
            status=SeatReservation.Status.ACTIVE,
            expires_at__gt=timezone.now(),
        ).order_by("seat_id", "-expires_at")
    }
    seat_data = []
    for section in sections:
        for row in section.rows.all():
            for seat in row.seats.all():
                seat_info = {
                    "id": str(seat.id),
                    "label": seat.label,
                    "section": section.name,
                    "row": row.name,
                    "number": seat.number,
                    "status": seat.status,
                    "is_available": seat.status == Seat.Status.AVAILABLE,
                    "is_accessible": seat.is_accessible,
                    "is_restricted_view": seat.is_restricted_view,
                    "section_ticket_price_minor": (
                        str(section.ticket_price_minor)
                        if section.ticket_price_minor is not None else None
                    ),
                    "section_price_modifier_minor": str(section.price_modifier_minor),
                }
                if seat.id in allocated_seat_ids:
                    seat_info.update(status="sold", is_available=False)
                active_reservation = active_reservations.get(seat.id)
                if active_reservation:
                    seat_info.update(
                        status="reserved",
                        is_available=False,
                        reservation_expires_at=active_reservation.expires_at.isoformat(),
                    )
                seat_data.append(seat_info)
    return seat_data


def default_reservation_expiry():
    minutes = getattr(settings, "SEATING_RESERVATION_MINUTES", 1440)
    return timezone.now() + timedelta(minutes=minutes)


def reserve_seats(*, event, seat_ids, session_key, reservation_minutes=None):
    """Atomically reserve seats for checkout.

    Uses PostgreSQL row-level locking (select_for_update) to prevent
    two checkout sessions from reserving the same seat simultaneously.

    Returns (reservations, errors) where reservations is a list of
    SeatReservation objects and errors is a list of error messages.
    """
    if reservation_minutes is None:
        reservation_minutes = getattr(settings, "SEATING_RESERVATION_MINUTES", 1440)
    seat_ids = [str(seat_id) for seat_id in seat_ids]

    expires_at = timezone.now() + timedelta(minutes=reservation_minutes)

    reservations = []
    errors = []

    with transaction.atomic():
        # Lock the seats for update to prevent concurrent reservations.
        # Only lock seats that belong to this event's venue.
        seats = Seat.objects.select_for_update().filter(
            id__in=seat_ids,
            row__section__venue__event_seatings__event=event,
        )

        found_seat_ids = {str(seat.id) for seat in seats}
        for seat_id in seat_ids:
            if seat_id not in found_seat_ids:
                errors.append(f"Seat {seat_id} not found for this event")

        for seat in seats:
            # Check physical seat status
            if seat.status != Seat.Status.AVAILABLE:
                errors.append(f"Seat {seat.label} is not available for booking")
                continue

            # Check for an active (non-expired) reservation
            existing = (
                SeatReservation.objects.select_for_update()
                .filter(seat=seat, status=SeatReservation.Status.ACTIVE)
                .first()
            )
            if existing:
                if existing.is_expired:
                    # Release expired reservation
                    existing.status = SeatReservation.Status.EXPIRED
                    existing.save(update_fields=["status", "updated_at"])
                else:
                    errors.append(f"Seat {seat.label} is temporarily reserved")
                    continue

            # Release any expired reservations for this seat
            SeatReservation.objects.filter(
                seat=seat, status=SeatReservation.Status.ACTIVE, expires_at__lte=timezone.now()
            ).update(status=SeatReservation.Status.EXPIRED)

            reservation = SeatReservation.objects.create(
                event=event,
                seat=seat,
                session_key=session_key,
                expires_at=expires_at,
                status=SeatReservation.Status.ACTIVE,
            )
            reservations.append(reservation)

        from ticketing.realtime import publish_inventory_update
        publish_inventory_update(event.id, seat_ids)

    return reservations, errors


def release_expired_reservations():
    """Mark all expired active reservations as expired.

    Called periodically by a Celery beat task or management command.
    Redis can coordinate the lock but PostgreSQL is the source of truth.
    """
    expired = SeatReservation.objects.filter(
        status=SeatReservation.Status.ACTIVE,
        expires_at__lte=timezone.now(),
    )
    count = expired.update(status=SeatReservation.Status.EXPIRED)
    for event_id in expired.values_list("event_id", flat=True).distinct():
        from ticketing.realtime import publish_inventory_update
        publish_inventory_update(event_id)
    return count


def release_reservations_for_session(*, session_key):
    """Release all active reservations held by a checkout session."""
    event_ids = list(SeatReservation.objects.filter(session_key=session_key, status=SeatReservation.Status.ACTIVE).values_list("event_id", flat=True).distinct())
    released = SeatReservation.objects.filter(
        session_key=session_key, status=SeatReservation.Status.ACTIVE
    ).update(status=SeatReservation.Status.RELEASED)
    # The session may contain reservations for multiple events; publish a safe refresh for each.
    for event_id in event_ids:
        from ticketing.realtime import publish_inventory_update
        publish_inventory_update(event_id)
    return released


def convert_reservation_to_allocation(*, reservation, ticket):
    """Convert an active seat reservation into a permanent seat allocation.

    Called after payment is verified. The reservation must be active and
    the seat must not already have an allocation.
    """
    if reservation.status != SeatReservation.Status.ACTIVE:
        raise ValueError("Only active reservations can be converted")

    with transaction.atomic():
        # Re-lock the seat to ensure it hasn't been reserved by someone else
        seat = Seat.objects.select_for_update().get(pk=reservation.seat_id)

        if seat.allocation_id is not None:
            raise ValueError("Seat already has an allocation")

        # Mark reservation as converted
        reservation.status = SeatReservation.Status.CONVERTED
        reservation.save(update_fields=["status", "updated_at"])

        # Create the allocation
        allocation = SeatAllocation.objects.create(seat=seat, ticket=ticket)

        # Update the ticket's seat reference and seat_label
        ticket.seat = seat
        ticket.seat_label = seat.label
        ticket.save(update_fields=["seat", "seat_label", "updated_at"])

        from ticketing.realtime import publish_inventory_update
        publish_inventory_update(ticket.event_id, [seat.id])

        return allocation


def get_event_seat_availability(event):
    """Return seat availability summary for an event's seating layout.

    Used by the organiser live occupancy dashboard.
    """
    try:
        event_seating = event.event_seating
    except AttributeError:
        return None

    seats = Seat.objects.filter(row__section__venue=event_seating.venue)
    total = seats.count()

    # Count allocated seats (sold)
    allocated = SeatAllocation.objects.filter(
        seat__in=seats
    ).count()

    # Count active reservations
    reserved = SeatReservation.objects.filter(
        seat__in=seats, status=SeatReservation.Status.ACTIVE,
        expires_at__gt=timezone.now(),
    ).count()

    # Count blocked seats
    blocked = seats.filter(status=Seat.Status.BLOCKED).count()
    unavailable = seats.filter(status=Seat.Status.UNAVAILABLE).count()
    available = total - allocated - reserved - blocked - unavailable

    return {
        "total": total,
        "sold": allocated,
        "reserved": reserved,
        "available": available,
        "blocked": blocked,
        "unavailable": unavailable,
        "occupancy_percentage": round((allocated / total * 100) if total else 0, 1),
    }
