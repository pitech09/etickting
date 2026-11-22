from django.conf import settings
from django.db import transaction


def calculate_order_total(order):
    """Calculate and set the order total from line items.

    This is the server-side price calculation — never trust prices
    submitted by the browser.
    """
    total = order.lines.aggregate(total=Sum("line_total_minor"))["total"] or 0
    subtotal = total
    # Add platform fee (e.g. 5%)
    platform_fee = int(subtotal * getattr(settings, "PLATFORM_FEE_PERCENT", 5) / 100)
    # Round to nearest minor currency unit
    fee_minor = max(platform_fee, 0)
    grand_total = subtotal + fee_minor

    with transaction.atomic():
        order.subtotal_minor = subtotal
        order.fee_minor = fee_minor
        order.total_minor = grand_total
        order.save(update_fields=["subtotal_minor", "fee_minor", "total_minor", "updated_at"])

    return {
        "subtotal_minor": subtotal,
        "fee_minor": fee_minor,
        "total_minor": grand_total,
    }


def get_seat_availability_json(event):
    """Return seat availability JSON for the checkout seating map.

    This queries PostgreSQL as the authority, not Redis.
    """
    from seating.services import get_event_seat_availability

    availability = get_event_seat_availability(event)
    if availability is None:
        return None

    # Also include section/row/seat details for the map
    from seating.models import Seat, SeatingSection, SeatingRow

    seats = Seat.objects.filter(
        row__section__venue=event.event_seating.venue,
        status=Seat.Status.AVAILABLE,
    ).select_related("row__section")

    seat_map = []
    for seat in seats:
        seat_map.append({
            "id": str(seat.id),
            "label": seat.label,
            "row": seat.row.name,
            "section": seat.row.section.name,
            "section_color": seat.row.section.color,
            "is_accessible": seat.is_accessible,
            "is_restricted_view": seat.is_restricted_view,
        })

    return {
        "availability": availability,
        "seat_map": seat_map,
    }