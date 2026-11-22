from django.db import transaction

from orders.fulfillment import fulfill_paid_order
from orders.models import Order

from .models import Payment


@transaction.atomic
def confirm_payment(*, payment_id, provider_reference, response=None):
    """Apply a verified provider result and fulfill the linked order once."""
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status == Payment.Status.SUCCESSFUL:
        return payment, list(payment.order.tickets.all())
    if payment.status not in {Payment.Status.PENDING, Payment.Status.INITIATED}:
        raise ValueError("Payment is not confirmable")
    if payment.amount_minor != payment.order.total_minor or payment.currency != payment.order.currency:
        raise ValueError("Payment amount or currency does not match the order")
    payment.mark_successful(provider_reference=provider_reference, response=response)
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if not order.mark_paid():
        raise ValueError("Order is not pending payment")
    tickets = fulfill_paid_order(order_id=order.id)
    return payment, tickets
