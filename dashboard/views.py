from functools import wraps
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Min, Q
from django.db.models import Count, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import date

from ticketing.models import Event
from payments.forms import PaymentReviewForm
from payments.models import Payment
from payments.services import confirm_payment


def organiser_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser or request.user.organisation_memberships.exists():
            return view(request, *args, **kwargs)
        return redirect("customer-dashboard")
    return wrapped


def customer_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser or request.user.organisation_memberships.exists():
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return wrapped


def _public_events():
    events = (
        Event.objects.filter(
            Q(status=Event.Status.PUBLISHED) | Q(status=Event.Status.SALES_OPEN)
        )
        .select_related("organisation", "venue")
        .prefetch_related("ticket_categories")
        .annotate(starting_price_minor=Min("ticket_categories__price_minor"))
        .order_by("starts_at")
    )
    for event in events:
        event.starting_price_maloti = (
            event.starting_price_minor / 100
            if event.starting_price_minor is not None
            else None
        )
    return events


def public_home(request):
    events = list(_public_events())
    return render(
        request,
        "public/home.html",
        {"featured_events": events[:3], "upcoming_events": events},
    )


def public_event_list(request):
    events = _public_events()
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    location = request.GET.get("location", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    if query:
        events = events.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(venue__name__icontains=query)
            | Q(venue__city__icontains=query)
        )
    if category:
        events = events.filter(ticket_categories__name__icontains=category)
    if location:
        events = events.filter(
            Q(venue__city__icontains=location) | Q(venue__name__icontains=location)
        )
    try:
        if date_from:
            events = events.filter(starts_at__date__gte=date.fromisoformat(date_from))
        if date_to:
            events = events.filter(starts_at__date__lte=date.fromisoformat(date_to))
    except ValueError:
        date_from = ""
        date_to = ""
    categories = (
        Event.objects.filter(
            Q(status=Event.Status.PUBLISHED) | Q(status=Event.Status.SALES_OPEN),
            ticket_categories__name__isnull=False,
        )
        .values_list("ticket_categories__name", flat=True)
        .distinct()
        .order_by("ticket_categories__name")
    )
    return render(
        request,
        "public/event_list.html",
        {
            "events": events.distinct(),
            "query": query,
            "category": category,
            "location": location,
            "date_from": date_from,
            "date_to": date_to,
            "categories": categories,
        },
    )


def public_event_detail(request, pk):
    event = get_object_or_404(_public_events(), pk=pk)
    return render(request, "public/event_detail.html", {"event": event})


@organiser_required
def dashboard(request):
    memberships = request.user.organisation_memberships.select_related("organisation")
    events = Event.objects.filter(organisation__memberships__user=request.user).select_related("organisation").order_by("starts_at")
    from orders.models import Order
    from ticketing.models import Ticket

    event_ids = events.values_list("id", flat=True)
    tickets = Ticket.objects.filter(event_id__in=event_ids)
    pending_payments = Order.objects.filter(
        event_id__in=event_ids, status=Order.Status.PENDING
    )
    revenue = Order.objects.filter(event_id__in=event_ids, status=Order.Status.PAID).aggregate(total=Sum("total_minor"))["total"] or 0
    sold = tickets.filter(status__in=[Ticket.Status.ISSUED, Ticket.Status.ADMITTED]).count()
    checked_in = tickets.filter(status=Ticket.Status.ADMITTED).count()
    available = sum(category.available_count for category in __import__("ticketing.models", fromlist=["TicketCategory"]).TicketCategory.objects.filter(event_id__in=event_ids))
    context = {
        "memberships": memberships,
        "primary_organisation": memberships.first().organisation if memberships.exists() else None,
        "events": events,
        "metrics": {"revenue_minor": Decimal(revenue) / Decimal("100"), "revenue_maloti": Decimal(revenue) / Decimal("100"), "tickets_sold": sold, "tickets_available": available, "check_ins": checked_in, "active_events": events.filter(status__in=[Event.Status.PUBLISHED, Event.Status.SALES_OPEN]).count(), "pending_payments": pending_payments.count()},
        "recent_orders": Order.objects.filter(event_id__in=event_ids).select_related("event", "customer")[:6],
    }
    return render(request, "dashboard/home.html", context)


@organiser_required
def pending_payments(request):
    """Show organiser-scoped orders awaiting payment confirmation."""
    from orders.models import Order

    orders = (
        Order.objects.filter(
            event__organisation__memberships__user=request.user,
            status=Order.Status.PENDING,
        )
        .select_related("event", "customer")
        .prefetch_related("payments")
        .order_by("created_at")
    )
    return render(request, "dashboard/pending_payments.html", {"orders": orders})


@organiser_required
def review_payment(request, payment_id):
    if request.method != "POST":
        return redirect("pending-payments")
    payment = get_object_or_404(
        Payment.objects.select_related("order__event__organisation"),
        pk=payment_id,
        order__event__organisation__memberships__user=request.user,
    )
    form = PaymentReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose whether to approve or reject this payment.")
        return redirect("pending-payments")
    note = form.cleaned_data["review_note"].strip()
    decision = form.cleaned_data["decision"]
    if payment.status not in {Payment.Status.PENDING, Payment.Status.INITIATED}:
        messages.error(request, "This payment has already been reviewed.")
        return redirect("pending-payments")
    try:
        with transaction.atomic():
            if decision == "approve":
                confirm_payment(
                    payment_id=payment.pk,
                    provider_reference=payment.provider_reference,
                    response={"method": "manual_review", "note": note},
                )
                message = "Payment approved and tickets issued."
            else:
                payment.mark_failed(reason=note or "Rejected during manual review")
                payment.order.status = payment.order.Status.FAILED
                payment.order.save(update_fields=["status", "updated_at"])
                payment.order.inventory_holds.filter(status="active").update(
                    status="released", updated_at=timezone.now()
                )
                message = "Payment rejected and the order was marked failed."
            payment.reviewed_at = timezone.now()
            payment.reviewed_by = request.user
            payment.review_note = note
            payment.save(update_fields=["reviewed_at", "reviewed_by", "review_note", "updated_at"])
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, message)
    return redirect("pending-payments")


@organiser_required
def payment_proof(request, payment_id):
    payment = get_object_or_404(
        Payment,
        pk=payment_id,
        order__event__organisation__memberships__user=request.user,
    )
    if not payment.proof_image:
        return redirect("pending-payments")
    return FileResponse(
        payment.proof_image.open("rb"),
        as_attachment=False,
        filename=payment.proof_image.name.rsplit("/", 1)[-1],
    )


@customer_required
def customer_dashboard(request):
    from orders.models import Order
    from ticketing.models import Ticket

    now = timezone.now()
    tickets = Ticket.objects.filter(owner=request.user).select_related("event", "ticket_category", "seat")
    orders = Order.objects.filter(customer=request.user).select_related("event")
    return render(request, "dashboard/customer.html", {
        "upcoming_tickets": tickets.filter(event__starts_at__gte=now, status=Ticket.Status.ISSUED).order_by("event__starts_at")[:6],
        "past_tickets": tickets.filter(event__starts_at__lt=now).order_by("-event__starts_at")[:6],
        "orders": orders[:6],
        "ticket_count": tickets.count(),
        "order_count": orders.count(),
    })
