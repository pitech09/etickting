import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
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
from seating.services import reserve_seats
from dashboard.views import customer_required
from payments.forms import ManualPaymentForm
from payments.models import Payment

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
                            reservations, errors = reserve_seats(
                                event=event,
                                seat_ids=[form.cleaned_data["seat"]],
                                session_key=request.session.session_key,
                            )
                            if errors or not reservations:
                                raise ValueError(errors[0] if errors else "That seat is no longer available.")
                            seat = Seat.objects.get(pk=form.cleaned_data["seat"])
                            OrderLine.objects.create(
                                order=order,
                                line_type=OrderLine.LineType.SEAT,
                                ticket_category=category,
                                seat=seat,
                                seat_reservation=reservations[0],
                                unit_price_minor=category.price_minor,
                                quantity=1,
                                line_total_minor=category.price_minor,
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
            initial={"seat": request.GET.get("seat")} if request.GET.get("seat") else None,
        )

    return render(request, "orders/order_create.html", {
        "form": form,
        "event": event,
        "idempotency_key": request.POST.get("idempotency_key", "") or uuid.uuid4().hex,
    })


@customer_required
def order_list(request):
    """List orders for the current user."""
    orders = request.user.orders.select_related("event").order_by("-created_at")
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
