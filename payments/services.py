from django.db import transaction

from orders.fulfillment import fulfill_paid_order
from orders.models import Order

from .models import Payment


def payment_status_for_order(order):
    payment = order.payments.order_by("-created_at").first()
    return {
        "order_reference": order.reference,
        "order_status": order.status,
        "payment_status": payment.status if payment else "not_submitted",
        "provider": payment.provider if payment else None,
        "submitted_at": payment.submitted_at.isoformat() if payment and payment.submitted_at else None,
    }


@transaction.atomic
def confirm_payment(*, payment_id, provider_reference, response=None, received_amount_minor=None):
    """Apply a verified provider result and fulfill the linked order once."""
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status == Payment.Status.SUCCESSFUL:
        if payment.provider_reference and provider_reference and payment.provider_reference.casefold() != provider_reference.casefold():
            raise ValueError("Payment callback reference does not match the confirmed payment")
        return payment, list(payment.order.tickets.all())
    if payment.status not in {Payment.Status.PENDING, Payment.Status.INITIATED}:
        raise ValueError("Payment is not confirmable")
    if payment.amount_minor != payment.order.total_minor or payment.currency != payment.order.currency:
        raise ValueError("Payment amount or currency does not match the order")
    if received_amount_minor is not None and received_amount_minor != payment.amount_minor:
        raise ValueError("The verified amount received does not match the order amount")
    if payment.provider_reference and provider_reference and payment.provider_reference != provider_reference:
        raise ValueError("Payment callback reference does not match the payment initiation")
    duplicate = Payment.objects.filter(
        provider_reference__iexact=provider_reference,
    ).exclude(pk=payment.pk).exclude(provider_reference="").first()
    if duplicate:
        raise ValueError("This provider reference has already been processed")
    payment.mark_successful(
        provider_reference=provider_reference,
        response=response,
        received_amount_minor=received_amount_minor,
    )
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    from orders.services import expire_order_if_holds_expired
    if expire_order_if_holds_expired(order):
        raise ValueError("The order's inventory reservation has expired")
    if not order.mark_paid():
        raise ValueError("Order is not pending payment")
    tickets = fulfill_paid_order(order_id=order.id)
    from finance.services import record_commission_for_payment
    record_commission_for_payment(payment=payment, order=order)
    return payment, tickets
