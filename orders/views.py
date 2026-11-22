import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
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

from .services import (
    calculate_order_total,
    get_seat_availability_json,
    process_payment_verification,
)


@login_required
@require_http_methods(["GET", "POST"])
def order_create(request, event_id):
    """Checkout view: create an order from a cart of tickets/seats."""
    event = get_object_or_404(Event, pk=event_id)

    # Check organisation membership
    if not request.user.organisations.filter(events=event).exists():
        messages.error(request, "You do not have access to this event.")
        return redirect("accounts:login")

    if request.method == "POST":
        form = OrderCreateForm(request.POST, event=event, user=request.user)
        if form.is_valid():
            order = form.save(commit=False)
            order.event = event
            order.customer = request.user
            order.save()
            messages.success(request, f"Order {order.reference} created successfully.")
            return redirect("orders:order-detail", pk=order.pk)
    else:
        # Build initial data from session cart or display available tickets
        form = OrderCreateForm(event=event, user=request.user)

    return render(request, "orders/order_create.html", {"form": form, "event": event})


@login_required
def order_list(request):
    """List orders for the current user."""
    orders = request.user.orders.select_related("event").order_by("-created_at")
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_detail(request, pk):
    """Display order details."""
    order = get_object_or_404(
        Order, pk=pk, customer=request.user
    )  # Security: only owner can view
    return render(request, "orders/order_detail.html", {"order": order})


@login_required
@require_POST
def order_cancel(request, pk):
    """Cancel an order."""
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.status == Order.Status.PAID:
        messages.error(request, "Paid orders cannot be cancelled.")
    else:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Order {order.reference} has been cancelled.")
    return redirect("orders:order-detail", pk=order.pk)


def order_confirmation(request, pk):
    """Show order confirmation page."""
    order = get_object_or_404(Order, pk=pk)
    # Security: check ownership
    if order.customer != request.user:
        messages.error(request, "You do not have access to this order.")
        return redirect("accounts:login")
    return render(request, "orders/order_confirmation.html", {"order": order})