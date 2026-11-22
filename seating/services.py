from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Seat, SeatAllocation, SeatReservation


def default_reservation_expiry():
    from django.conf import settings

    minutes = getattr(settings, "SEATING_RESERVATION_MINUTES", 10)
    return timezone.now() + timedelta(minutes=minutes)


def reserve_seats(*, event, seat_ids, session_key, reservation_minutes=None):
    """Atomically reserve seats for checkout.

    Uses PostgreSQL row-level locking (select_for_update) to prevent
    two checkout sessions from reserving the same seat simultaneously.

    Returns (reservations, errors) where reservations is a list of
    SeatReservation objects and errors is a list of error messages.
    """
    if reservation_minutes is None:
        reservation_minutes = 10

    expires_at = timezone.now() + timedelta(minutes=reservation_minutes)

    reservations = []
    errors = []

    with transaction.atomic():
        # Lock the seats for update to prevent concurrent reservations.
        # Only lock seats that belong to this event's venue.
        seats = Seat.objects.select_for_update().filter(
            id__in=seat_ids,
            row__section__venue__event_seatings__event=event,
        ).distinct()

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
    return count


def release_reservations_for_session(*, session_key):
    """Release all active reservations held by a checkout session."""
    released = SeatReservation.objects.filter(
        session_key=session_key, status=SeatReservation.Status.ACTIVE
    ).update(status=SeatReservation.Status.RELEASED)
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