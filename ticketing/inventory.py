from django.db.models import Q, Sum
from django.utils import timezone

from .models import Event, Ticket


def inventory_snapshot(event):
    """Build an organiser-scoped snapshot from PostgreSQL-backed inventory."""
    active_statuses = (Ticket.Status.ISSUED, Ticket.Status.ADMITTED)
    categories = []
    for category in event.ticket_categories.all():
        sold = category.tickets.filter(status__in=active_statuses).count()
        categories.append({
            "id": str(category.id),
            "name": category.name,
            "price_minor": category.price_minor,
            "sold": sold,
            "available": max(0, category.total_quantity - sold),
            "total": category.total_quantity,
            "revenue_minor": sold * category.price_minor,
        })

    snapshot = {
        "event_id": str(event.id),
        "event_name": event.name,
        "generated_at": timezone.now().isoformat(),
        "general_admission": categories,
        "seating": None,
    }
    try:
        event_seating = event.event_seating
    except Event.event_seating.RelatedObjectDoesNotExist:
        return snapshot

    from seating.models import Seat, SeatAllocation, SeatReservation

    seats = Seat.objects.filter(row__section__venue=event_seating.venue).select_related("row__section")
    now = timezone.now()
    allocated = set(SeatAllocation.objects.filter(seat__in=seats).values_list("seat_id", flat=True))
    reserved = dict(SeatReservation.objects.filter(seat__in=seats, status=SeatReservation.Status.ACTIVE, expires_at__gt=now).values_list("seat_id", "expires_at"))
    seat_items = []
    counts = {"total": 0, "sold": 0, "reserved": 0, "available": 0, "blocked": 0, "unavailable": 0}
    for seat in seats:
        counts["total"] += 1
        if seat.status == Seat.Status.BLOCKED:
            state = "blocked"
        elif seat.status == Seat.Status.UNAVAILABLE:
            state = "unavailable"
        elif seat.id in allocated:
            state = "sold"
        elif seat.id in reserved:
            state = "reserved"
        else:
            state = "available"
        counts[state] += 1
        seat_items.append({
            "id": str(seat.id), "label": seat.label, "section": seat.row.section.name,
            "row": seat.row.name, "state": state,
            "reservation_expires_at": reserved[seat.id].isoformat() if seat.id in reserved else None,
        })
    counts["occupancy_percentage"] = round((counts["sold"] / counts["total"] * 100) if counts["total"] else 0, 1)
    snapshot["seating"] = {"metrics": counts, "seats": seat_items}
    return snapshot
