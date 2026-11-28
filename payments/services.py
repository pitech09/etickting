from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.urls import reverse

from orders.fulfillment import fulfill_paid_order
from orders.models import Order

from .models import Payment
from .models import RefundRequest


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
    provider_reference = str(provider_reference or "").strip()
    if not provider_reference:
        raise ValueError("A provider transaction reference is required to confirm payment")
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
    if payment.provider_reference and payment.provider_reference.casefold() != provider_reference.casefold():
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


ACTIVE_REFUND_STATUSES = {
    RefundRequest.Status.REQUESTED,
    RefundRequest.Status.UNDER_REVIEW,
    RefundRequest.Status.APPROVED,
    RefundRequest.Status.PROCESSING,
    RefundRequest.Status.COMPLETED,
}


def _refund_reviewer_can_access(user, order):
    if user.is_staff or user.is_superuser:
        return True
    from organisations.models import OrganisationMembership

    return OrganisationMembership.objects.filter(
        organisation=order.event.organisation,
        user=user,
        role__in=("owner", "event_manager"),
    ).exists()


def _remaining_refundable_amount(order, *, exclude=None, reserve_requested=True):
    statuses = ACTIVE_REFUND_STATUSES if reserve_requested else {
        RefundRequest.Status.APPROVED,
        RefundRequest.Status.PROCESSING,
        RefundRequest.Status.COMPLETED,
    }
    requests = order.refund_requests.filter(status__in=statuses)
    if exclude is not None:
        requests = requests.exclude(pk=exclude.pk)
    reserved = requests.aggregate(total=Sum("requested_amount_minor"))["total"] or Decimal("0.00")
    if not reserve_requested:
        reserved = requests.aggregate(total=Sum("approved_amount_minor"))["total"] or Decimal("0.00")
    return max(Decimal("0.00"), Decimal(str(order.total_minor)) - Decimal(str(reserved)))


@transaction.atomic
def request_refund(*, order_id, requester, amount_minor, reason, is_event_cancellation=False):
    from orders.models import Order

    order = Order.objects.select_for_update().select_related("event").get(pk=order_id)
    if order.customer_id != requester.id:
        raise PermissionDenied("Only the customer who placed the order can request a refund")
    if order.status != Order.Status.PAID:
        raise ValueError("Only paid orders can receive a refund request")
    payment = order.payments.filter(status=Payment.Status.SUCCESSFUL).order_by("-created_at").first()
    if not payment:
        raise ValueError("A verified successful payment is required before requesting a refund")
    try:
        amount = Decimal(str(amount_minor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Refund amount must be a valid number") from exc
    if amount <= 0:
        raise ValueError("Refund amount must be greater than zero")
    if amount > _remaining_refundable_amount(order):
        raise ValueError("The requested refund exceeds the remaining refundable amount")
    if not str(reason or "").strip():
        raise ValueError("Explain why a refund is requested")
    existing_request = order.refund_requests.filter(
        requester=requester,
        requested_amount_minor=amount,
        reason=str(reason).strip(),
        status__in=ACTIVE_REFUND_STATUSES,
    ).first()
    if existing_request:
        return existing_request
    if is_event_cancellation:
        existing = order.refund_requests.filter(is_event_cancellation=True).first()
        if existing:
            return existing
    return RefundRequest.objects.create(
        order=order,
        payment=payment,
        requester=requester,
        requested_amount_minor=amount,
        reason=str(reason).strip(),
        is_event_cancellation=is_event_cancellation,
    )


@transaction.atomic
def create_event_cancellation_refunds(*, event, actor):
    from orders.models import Order

    created = []
    orders = Order.objects.select_for_update().filter(
        event=event,
        status=Order.Status.PAID,
    ).prefetch_related("payments")
    for order in orders:
        refund = order.refund_requests.filter(is_event_cancellation=True).first()
        if refund:
            created.append(refund)
            continue
        payment = order.payments.filter(status=Payment.Status.SUCCESSFUL).order_by("-created_at").first()
        if not payment:
            continue
        refund = RefundRequest.objects.create(
            order=order,
            payment=payment,
            requester=order.customer,
            requested_amount_minor=order.total_minor,
            reason=f"Full refund entitlement created because event {event.name} was cancelled.",
            is_event_cancellation=True,
        )
        try:
            from notifications.services import notify

            notify(
                user=order.customer,
                title="Event cancelled — refund entitlement created",
                message=(
                    f"{event.name} was cancelled. Refund request {refund.id} was created for "
                    f"M {refund.requested_amount_minor:.2f}. It remains subject to processing confirmation."
                ),
                action_url=reverse("customer-refunds"),
            )
            refund.notification_status = RefundRequest.NotificationStatus.SENT
        except Exception as exc:
            refund.notification_status = RefundRequest.NotificationStatus.FAILED
            refund.notification_error = exc.__class__.__name__
        refund.save(update_fields=["notification_status", "notification_error", "updated_at"])
        created.append(refund)
    return created


@transaction.atomic
def review_refund(*, refund_id, reviewer, decision, approved_amount_minor=None, note=""):
    refund = RefundRequest.objects.select_for_update().select_related("order__event").get(pk=refund_id)
    if not _refund_reviewer_can_access(reviewer, refund.order):
        raise PermissionDenied("You cannot review refunds for this organisation")
    if refund.status not in {RefundRequest.Status.REQUESTED, RefundRequest.Status.UNDER_REVIEW}:
        raise ValueError("This refund is no longer awaiting review")
    note = str(note or "").strip()
    if decision == "reject":
        if not note:
            raise ValueError("Explain why the refund was rejected")
        refund.status = RefundRequest.Status.REJECTED
        refund.review_note = note
        refund.reviewer = reviewer
        refund.reviewed_at = timezone.now()
    elif decision == "approve":
        try:
            amount = Decimal(str(approved_amount_minor if approved_amount_minor is not None else refund.requested_amount_minor))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Approved refund amount must be a valid number") from exc
        if amount <= 0:
            raise ValueError("Approved refund amount must be greater than zero")
        if amount > _remaining_refundable_amount(refund.order, exclude=refund, reserve_requested=False):
            raise ValueError("The approved refund exceeds the remaining refundable amount")
        refund.status = RefundRequest.Status.APPROVED
        refund.approved_amount_minor = amount
        refund.review_note = note
        refund.reviewer = reviewer
        refund.reviewed_at = timezone.now()
    else:
        raise ValueError("Unknown refund decision")
    refund.save(update_fields=["status", "approved_amount_minor", "review_note", "reviewer", "reviewed_at", "updated_at"])
    from audit.services import record

    record(action=f"refund_{decision}", actor=reviewer, obj=refund, metadata={"amount": str(refund.approved_amount_minor or refund.requested_amount_minor), "note": note})
    return refund


@transaction.atomic
def start_refund_processing(*, refund_id, actor, note=""):
    refund = RefundRequest.objects.select_for_update().select_related("order").get(pk=refund_id)
    if not _refund_reviewer_can_access(actor, refund.order):
        raise PermissionDenied("You cannot process refunds for this organisation")
    if refund.status != RefundRequest.Status.APPROVED:
        raise ValueError("Only approved refunds can enter processing")
    refund.status = RefundRequest.Status.PROCESSING
    refund.processing_at = timezone.now()
    refund.executor = actor
    refund.execution_note = str(note or "").strip()
    refund.save(update_fields=["status", "processing_at", "executor", "execution_note", "updated_at"])
    return refund


@transaction.atomic
def complete_refund(*, refund_id, actor, provider_reference, note=""):
    from orders.models import Order
    from ticketing.models import Ticket

    refund = RefundRequest.objects.select_for_update().select_related("order", "payment").get(pk=refund_id)
    if not _refund_reviewer_can_access(actor, refund.order):
        raise PermissionDenied("You cannot complete refunds for this organisation")
    if refund.status != RefundRequest.Status.PROCESSING:
        raise ValueError("Only processing refunds can be completed")
    provider_reference = str(provider_reference or "").strip()
    if not provider_reference:
        raise ValueError("Record the actual refund provider reference before completion")
    refund.status = RefundRequest.Status.COMPLETED
    refund.provider_reference = provider_reference
    refund.execution_note = str(note or "").strip()
    refund.executor = actor
    refund.completed_at = timezone.now()
    refund.save(update_fields=["status", "provider_reference", "execution_note", "executor", "completed_at", "updated_at"])
    amount = Decimal(str(refund.approved_amount_minor))
    completed_before = RefundRequest.objects.filter(
        order=refund.order,
        status=RefundRequest.Status.COMPLETED,
    ).exclude(pk=refund.pk).aggregate(total=Sum("approved_amount_minor"))["total"] or Decimal("0.00")
    if completed_before + amount >= Decimal(str(refund.order.total_minor)):
        refund.order.status = Order.Status.REFUNDED
        refund.order.save(update_fields=["status", "updated_at"])
        refund.payment.status = Payment.Status.REFUNDED
        refund.payment.save(update_fields=["status", "updated_at"])
        Ticket.objects.filter(order=refund.order).exclude(status=Ticket.Status.REFUNDED).update(status=Ticket.Status.REFUNDED, updated_at=timezone.now())
    from finance.services import record_refund_commission_reversal

    record_refund_commission_reversal(refund=refund, actor=actor)
    from audit.services import record

    record(action="refund_completed", actor=actor, obj=refund, metadata={"amount": str(amount), "provider_reference": provider_reference})
    return refund


@transaction.atomic
def fail_refund(*, refund_id, actor, note):
    refund = RefundRequest.objects.select_for_update().select_related("order").get(pk=refund_id)
    if not _refund_reviewer_can_access(actor, refund.order):
        raise PermissionDenied("You cannot update refunds for this organisation")
    if refund.status != RefundRequest.Status.PROCESSING:
        raise ValueError("Only processing refunds can be marked failed")
    note = str(note or "").strip()
    if not note:
        raise ValueError("Explain why the refund requires intervention")
    refund.status = RefundRequest.Status.FAILED
    refund.execution_note = note
    refund.executor = actor
    refund.save(update_fields=["status", "execution_note", "executor", "updated_at"])
    return refund
