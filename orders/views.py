import uuid
import logging
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Min, Prefetch
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView

from orders.forms import OrderCreateForm
from orders.models import Order, OrderLine
from ticketing.models import Event, TicketCategory, Ticket
from seating.models import Seat
from seating.services import calculate_seat_price, get_customer_seat_map_data, reserve_seats
from dashboard.views import customer_required
from payments.forms import ManualPaymentForm
from payments.models import Payment, RefundRequest

logger = logging.getLogger(__name__)

from .services import (
    calculate_order_total,
    expire_order_if_holds_expired,
    get_seat_availability_json,
    hold_general_admission,
)


@customer_required
@require_http_methods(["GET", "POST"])
def order_create(request, event_id):
    """Checkout view: create an order from a cart of tickets/seats."""
    event = get_object_or_404(Event, pk=event_id)

    if not event.sales_are_open():
        messages.error(request, "This event is not currently available for booking.")
        return redirect("public-event-detail", pk=event.pk)

    if request.method == "POST":
        form = OrderCreateForm(request.POST, event=event, user=request.user)
        if form.is_valid():
            idempotency_key = request.POST.get("idempotency_key", "").strip() or uuid.uuid4().hex
            existing = Order.objects.filter(
                idempotency_key=idempotency_key, customer=request.user
            ).first()
            if existing:
                return redirect("orders:order-detail", pk=existing.pk)
            if Order.objects.filter(idempotency_key=idempotency_key).exists():
                form.add_error(None, "That checkout request belongs to another customer.")
            else:
                try:
                    with transaction.atomic():
                        category = TicketCategory.objects.select_for_update().filter(
                            pk=form.cleaned_data["ticket_category"], event=event, is_active=True
                        ).first()
                        if not category:
                            raise ValueError("That ticket category is no longer available.")
                        try:
                            category_price = Decimal(str(category.price_minor))
                        except (InvalidOperation, TypeError, ValueError) as exc:
                            logger.warning("Invalid price for ticket category %s on event %s", category.pk, event.pk, exc_info=exc)
                            raise ValueError("Pricing is currently unavailable for this ticket category.") from exc
                        if category_price < 0:
                            logger.warning("Negative price for ticket category %s on event %s", category.pk, event.pk)
                            raise ValueError("Pricing is currently unavailable for this ticket category.")
                        now = timezone.now()
                        if category.sales_opens_at and now < category.sales_opens_at:
                            raise ValueError("This ticket category is not on sale yet.")
                        if category.sales_closes_at and now > category.sales_closes_at:
                            raise ValueError("Sales for this ticket category have closed.")
                        quantity = form.cleaned_data.get("quantity") or 1
                        if quantity > category.max_per_customer:
                            raise ValueError(f"You can purchase at most {category.max_per_customer} of this ticket.")
                        order = Order.objects.create(
                            event=event,
                            customer=request.user,
                            idempotency_key=idempotency_key,
                        )
                        request.session.save()
                        if event.ticketing_model == Event.TicketingModel.RESERVED_SEATING:
                            seat_ids = form.cleaned_data.get("seat_ids", [])
                            if len(seat_ids) != quantity:
                                raise ValueError(f"Choose exactly {quantity} seat(s) on the seating map.")
                            reservations, errors = reserve_seats(
                                event=event,
                                seat_ids=seat_ids,
                                session_key=request.session.session_key,
                            )
                            if errors or len(reservations) != quantity:
                                raise ValueError(errors[0] if errors else "That seat is no longer available.")
                            reservations_by_seat = {str(reservation.seat_id): reservation for reservation in reservations}
                            seats = Seat.objects.select_related("row__section").filter(pk__in=seat_ids)
                            seats_by_id = {str(seat.id): seat for seat in seats}
                            for seat_id in seat_ids:
                                seat = seats_by_id[seat_id]
                                reservation = reservations_by_seat[seat_id]
                                unit_price = calculate_seat_price(category=category, seat=seat)
                                OrderLine.objects.create(
                                    order=order,
                                    line_type=OrderLine.LineType.SEAT,
                                    ticket_category=category,
                                    seat=seat,
                                    seat_reservation=reservation,
                                    unit_price_minor=unit_price,
                                    quantity=1,
                                    line_total_minor=unit_price,
                                )
                        else:
                            hold_general_admission(
                                order=order,
                                category=category,
                                quantity=quantity,
                                session_key=request.session.session_key,
                            )
                            OrderLine.objects.create(
                                order=order,
                                line_type=OrderLine.LineType.TICKET_CATEGORY,
                                ticket_category=category,
                                unit_price_minor=category.price_minor,
                                quantity=quantity,
                                line_total_minor=category.price_minor * quantity,
                            )
                        calculate_order_total(order)
                except IntegrityError:
                    existing = Order.objects.filter(
                        idempotency_key=idempotency_key, customer=request.user
                    ).first()
                    if existing:
                        return redirect("orders:order-detail", pk=existing.pk)
                    raise
                except ValueError as exc:
                    form.add_error(None, str(exc))
                else:
                    messages.success(request, f"Order {order.reference} created. Complete payment to receive your tickets.")
                    return redirect("orders:order-detail", pk=order.pk)
    else:
        # Build initial data from session cart or display available tickets
        form = OrderCreateForm(
            event=event,
            user=request.user,
            initial={
                "ticket_category": request.GET.get("ticket_category", ""),
                "quantity": request.GET.get("quantity", "1"),
                "seat_ids": request.GET.get("seat_ids", ""),
            },
        )

    selected_seat_ids = [value.strip() for value in (request.POST.get("seat_ids") or request.GET.get("seat_ids") or "").split(",") if value.strip()]
    selected_seats = Seat.objects.filter(pk__in=selected_seat_ids).select_related("row__section") if selected_seat_ids else []
    ticket_categories = list(
        event.ticket_categories.filter(is_active=True).values(
            "id", "name", "price_minor", "max_per_customer"
        )
    )
    pricing_unavailable = not ticket_categories or any(
        category["price_minor"] is None or category["price_minor"] < 0
        for category in ticket_categories
    )
    if pricing_unavailable:
        logger.warning("Pricing unavailable for event %s during checkout", event.pk)
    return render(request, "orders/order_create.html", {
        "form": form,
        "event": event,
        "selected_seats": selected_seats,
        "reserved_seat_modifiers": [str(seat.row.section.price_modifier_minor) for seat in selected_seats],
        "idempotency_key": request.POST.get("idempotency_key", "") or uuid.uuid4().hex,
        "ticket_price_data": {
            str(category.id): str(category.price_minor)
            for category in TicketCategory.objects.filter(event=event, is_active=True)
        },
        "ticket_categories": ticket_categories,
        "pricing_unavailable": pricing_unavailable,
        "seat_data": get_customer_seat_map_data(event)
        if event.ticketing_model == Event.TicketingModel.RESERVED_SEATING
        else [],
    })


@customer_required
def order_list(request):
    """List orders for the current user."""
    orders = request.user.orders.select_related("event").annotate(ticket_count=Count("tickets")).prefetch_related(
        Prefetch("payments", queryset=Payment.objects.order_by("-created_at"), to_attr="payment_history"),
        Prefetch("refund_requests", queryset=RefundRequest.objects.order_by("-requested_at"), to_attr="refund_history"),
    ).order_by("-created_at")
    return render(request, "orders/order_list.html", {"orders": orders})


@customer_required
@require_http_methods(["GET", "POST"])
def order_detail(request, pk):
    """Display order details."""
    order = get_object_or_404(
        Order.objects.select_related("event__organisation").prefetch_related("lines__ticket_category", "lines__seat", "payments"),
        pk=pk,
        customer=request.user,
    )
    expire_order_if_holds_expired(order)
    order.refresh_from_db()
    reservation_expires_at = order.inventory_holds.filter(
        status="active", expires_at__gt=timezone.now(),
    ).aggregate(expires_at=Min("expires_at"))["expires_at"]
    seat_expiry = order.lines.filter(
        seat_reservation__status="active", seat_reservation__expires_at__gt=timezone.now(),
    ).aggregate(expires_at=Min("seat_reservation__expires_at"))["expires_at"]
    if seat_expiry and (not reservation_expires_at or seat_expiry < reservation_expires_at):
        reservation_expires_at = seat_expiry
    form = ManualPaymentForm(organisation=order.event.organisation)
    if request.method == "POST":
        if order.status != Order.Status.PENDING:
            messages.error(request, "This order is no longer awaiting payment.")
        else:
            payment = order.payments.filter(
                status__in=[Payment.Status.PENDING, Payment.Status.INITIATED]
            ).first()
            form = ManualPaymentForm(
                request.POST,
                request.FILES,
                instance=payment,
                organisation=order.event.organisation,
            )
            if form.is_valid():
                payment = form.save(commit=False)
                payment.order = order
                payment.provider = form.cleaned_data["payment_method"].provider
                payment.sender_phone = form.cleaned_data["sender_phone"]
                payment.amount_minor = order.total_minor
                payment.currency = order.currency
                payment.status = Payment.Status.PENDING
                payment.idempotency_key = (
                    request.headers.get("Idempotency-Key", "").strip()
                    or payment.idempotency_key
                    or uuid.uuid4().hex
                )
                payment.submitted_at = timezone.now()
                payment.save()
                messages.success(request, "Your payment proof was submitted for organiser review.")
                return redirect("orders:order-detail", pk=order.pk)
    pending_over_24h = (
        order.status == Order.Status.PENDING
        and order.created_at <= timezone.now() - timedelta(hours=24)
    )
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "payment_form": form,
            "pending_over_24h": pending_over_24h,
            "support_email": settings.SUPPORT_EMAIL,
            "payment_methods": order.event.organisation.payment_methods.filter(is_active=True),
            "payment": order.payments.order_by("-created_at").first(),
            "reservation_expires_at": reservation_expires_at,
        },
    )


@customer_required
def payment_status(request, pk):
    from payments.services import payment_status_for_order

    order = get_object_or_404(Order.objects.select_related("event"), pk=pk, customer=request.user)
    return JsonResponse(payment_status_for_order(order))


@customer_required
@require_POST
def order_cancel(request, pk):
    """Cancel an order."""
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.status == Order.Status.PAID:
        messages.error(request, "Paid orders cannot be cancelled.")
    else:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        order.inventory_holds.filter(status="active").update(status="released", updated_at=timezone.now())
        messages.success(request, f"Order {order.reference} has been cancelled.")
    return redirect("orders:order-detail", pk=order.pk)


@customer_required
def order_confirmation(request, pk):
    """Show order confirmation page."""
    order = get_object_or_404(Order, pk=pk)
    # Security: check ownership
    if order.customer != request.user:
        messages.error(request, "You do not have access to this order.")
        return redirect("accounts:login")
    return render(request, "orders/order_confirmation.html", {"order": order})
