from django.db import transaction
from django.utils import timezone

from ticketing.models import Ticket
from ticketing.services import issue_ticket
from seating.models import SeatAllocation, SeatReservation

from .models import Order, InventoryHold


@transaction.atomic
def fulfill_paid_order(*, order_id):
    """Issue exactly one set of tickets for a paid order.

    Repeated provider callbacks return existing tickets instead of issuing
    duplicates. This function must only be called after provider verification.
    """
    order = Order.objects.select_for_update().select_related("event", "customer").get(pk=order_id)
    existing = list(Ticket.objects.filter(order_id=order.id))
    if existing:
        return existing
    if order.status != Order.Status.PAID:
        raise ValueError("Only paid orders can be fulfilled")

    issued = []
    for line in order.lines.select_related("ticket_category", "seat", "seat_reservation"):
        for _ in range(line.quantity):
            if line.seat_id:
                reservation_filter = {
                    "event": order.event,
                    "seat_id": line.seat_id,
                    "status": SeatReservation.Status.ACTIVE,
                }
                if line.seat_reservation_id:
                    reservation_filter["pk"] = line.seat_reservation_id
                reservation = SeatReservation.objects.select_for_update().filter(
                    **reservation_filter
                ).first()
                if not reservation or reservation.expires_at <= timezone.now():
                    raise ValueError("The reserved seat hold has expired; payment cannot issue this ticket")
            ticket, _credential = issue_ticket(
                event=order.event,
                owner=order.customer,
                payment_verified=True,
                ticket_category=line.ticket_category,
                seat=line.seat,
                seat_label=line.seat.label if line.seat else "",
            )
            ticket.order_id = order.id
            ticket.save(update_fields=["order_id", "updated_at"])
            if line.seat_id:
                reservation.status = SeatReservation.Status.CONVERTED
                reservation.save(update_fields=["status", "updated_at"])
                SeatAllocation.objects.create(seat=line.seat, ticket=ticket)
            issued.append(ticket)
    order.inventory_holds.filter(status=InventoryHold.Status.ACTIVE).update(
        status=InventoryHold.Status.CONVERTED, updated_at=timezone.now()
    )
    return issued
