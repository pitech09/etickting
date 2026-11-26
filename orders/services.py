from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import InventoryHold


def expire_order_if_holds_expired(order):
    """Expire a pending order once all of its inventory reservations have ended."""
    if order.status != order.Status.PENDING:
        return False
    now = timezone.now()
    has_inventory = order.inventory_holds.exists() or order.lines.filter(seat_reservation__isnull=False).exists()
    if not has_inventory:
        return False
    has_active_hold = order.inventory_holds.filter(
        status=InventoryHold.Status.ACTIVE,
        expires_at__gt=now,
    ).exists()
    has_active_seat = order.lines.filter(
        seat_reservation__status="active",
        seat_reservation__expires_at__gt=now,
    ).exists()
    if has_active_hold or has_active_seat:
        return False
    order.status = order.Status.EXPIRED
    order.save(update_fields=["status", "updated_at"])
    order.inventory_holds.filter(status=InventoryHold.Status.ACTIVE).update(
        status=InventoryHold.Status.EXPIRED,
        updated_at=now,
    )
    return True


def release_expired_inventory_holds():
    """Release expired GA holds; safe to run from a scheduled worker."""
    return InventoryHold.objects.filter(
        status=InventoryHold.Status.ACTIVE, expires_at__lte=timezone.now()
    ).update(status=InventoryHold.Status.EXPIRED, updated_at=timezone.now())


def hold_general_admission(*, order, category, quantity, session_key="", minutes=None):
    """Create an atomic GA hold after checking issued tickets and active holds."""
    from ticketing.models import Ticket

    minutes = minutes or getattr(settings, "TICKETING_HOLD_MINUTES", 10)
    now = timezone.now()
    expires_at = now + timedelta(minutes=minutes)
    from ticketing.models import TicketCategory

    category = TicketCategory.objects.select_for_update().get(pk=category.pk)
    InventoryHold.objects.filter(
        ticket_category=category,
        status=InventoryHold.Status.ACTIVE,
        expires_at__lte=now,
    ).update(status=InventoryHold.Status.EXPIRED, updated_at=now)
    sold = Ticket.objects.filter(
        ticket_category=category,
        status__in=[Ticket.Status.ISSUED, Ticket.Status.ADMITTED],
    ).count()
    held = InventoryHold.objects.filter(
        ticket_category=category,
        status=InventoryHold.Status.ACTIVE,
        expires_at__gt=now,
    ).aggregate(total=Sum("quantity"))["total"] or 0
    if sold + held + quantity > category.total_quantity:
        raise ValueError("There are not enough tickets available.")
    return InventoryHold.objects.create(
        order=order,
        ticket_category=category,
        quantity=quantity,
        session_key=session_key,
        expires_at=expires_at,
    )


def calculate_order_total(order):
    """Calculate and set the order total from line items.

    This is the server-side price calculation — never trust prices
    submitted by the browser.
    """
    total = order.lines.aggregate(total=Sum("line_total_minor"))["total"] or 0
    subtotal = total
    from finance.services import calculate_commission, current_commission_rate
    commission_rate = current_commission_rate()
    commission_minor = calculate_commission(subtotal, commission_rate)
    fee_minor = Decimal("0.00")
    grand_total = subtotal
    organiser_net_minor = max(Decimal("0.00"), subtotal - commission_minor)

    with transaction.atomic():
        order.subtotal_minor = subtotal
        order.fee_minor = fee_minor
        order.commission_rate = commission_rate
        order.commission_minor = commission_minor
        order.organiser_net_minor = organiser_net_minor
        order.total_minor = grand_total
        order.save(update_fields=["subtotal_minor", "fee_minor", "commission_rate", "commission_minor", "organiser_net_minor", "total_minor", "updated_at"])

    return {
        "subtotal_minor": subtotal,
        "fee_minor": fee_minor,
        "commission_rate": commission_rate,
        "commission_minor": commission_minor,
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
