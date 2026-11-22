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
    for line in order.lines.select_related("ticket_category", "seat"):
        for _ in range(line.quantity):
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
                SeatAllocation.objects.create(seat=line.seat, ticket=ticket)
                SeatReservation.objects.filter(
                    event=order.event,
                    seat=line.seat,
                    status=SeatReservation.Status.ACTIVE,
                ).update(status=SeatReservation.Status.CONVERTED, updated_at=timezone.now())
            issued.append(ticket)
    order.inventory_holds.filter(status=InventoryHold.Status.ACTIVE).update(
        status=InventoryHold.Status.CONVERTED, updated_at=timezone.now()
    )
    return issued
