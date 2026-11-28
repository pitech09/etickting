from functools import wraps
from decimal import Decimal
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.files.storage import default_storage
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Min, Q
from django.db.models import Count, Sum
from django.http import FileResponse
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import date

from ticketing.models import Event
from ticketing.models import Ticket
import csv
from payments.forms import PaymentReviewForm
from payments.models import Payment, PaymentReview
from payments.services import (
    complete_refund,
    confirm_payment,
    fail_refund,
    request_refund as create_refund_request,
    review_refund,
    start_refund_processing,
)


def organiser_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser or request.user.organisation_memberships.exists():
            return view(request, *args, **kwargs)
        return redirect("customer-dashboard")
    return wrapped


def payment_reviewer_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_superuser or request.user.is_staff:
            return view(request, *args, **kwargs)
        if not request.user.organisation_memberships.exists():
            return redirect("customer-dashboard")
        if not request.user.organisation_memberships.filter(
            role__in=("owner", "event_manager")
        ).exists():
            raise PermissionDenied("Only organisation owners and event managers can review payments")
        return view(request, *args, **kwargs)
    return wrapped


def customer_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser or request.user.organisation_memberships.exists():
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return wrapped


def platform_owner_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


@platform_owner_required
def platform_dashboard(request):
    from accounts.models import User
    from audit.models import AuditLog
    from finance.models import CommissionTransaction, LedgerEntry, Payout, PlatformCommissionConfig
    from organisations.models import Organisation, OrganisationMembership
    from orders.models import Order
    from payments.models import Payment
    from ticketing.models import ScanAttempt
    from ticketing.models import Ticket

    database_ready = False
    try:
        connection.ensure_connection()
        database_ready = True
    except Exception:
        pass

    redis_ready = False
    if settings.REDIS_CONFIGURED:
        try:
            cache.set("platform-readiness-check", "ok", 5)
            redis_ready = cache.get("platform-readiness-check") == "ok"
        except Exception:
            pass

    try:
        from ticketing.key_management import signing_keys, verification_keys

        signing_key_ids = list(signing_keys())
        verification_key_ids = list(verification_keys())
        key_error = ""
    except Exception as exc:
        signing_key_ids = []
        verification_key_ids = []
        key_error = str(exc)

    try:
        pending_migrations = len(MigrationExecutor(connection).migration_plan(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        ))
    except Exception:
        pending_migrations = None

    paid_orders = Order.objects.filter(status=Order.Status.PAID)
    refunded_payments = Payment.objects.filter(status=Payment.Status.REFUNDED)
    failed_scans = ScanAttempt.objects.filter(
        result__in=[ScanAttempt.Result.INVALID, ScanAttempt.Result.UNAUTHORISED]
    )
    organisations = Organisation.objects.order_by("name")[:12]
    users = User.objects.order_by("-date_joined")[:20]
    events = Event.objects.select_related("organisation").order_by("-starts_at")[:20]
    recent_audit = AuditLog.objects.select_related("actor")[:20]
    recent_scans = failed_scans.select_related("event", "scanner", "device")[:20]

    context = {
        "metrics": {
            "users": User.objects.count(),
            "organisations": Organisation.objects.count(),
            "events": Event.objects.count(),
            "orders": Order.objects.count(),
            "tickets": Ticket.objects.count(),
            "admitted_tickets": Ticket.objects.filter(status=Ticket.Status.ADMITTED).count(),
        },
        "health": {
            "database": database_ready,
            "redis": redis_ready,
            "redis_configured": settings.REDIS_CONFIGURED,
            "object_storage": settings.USE_OBJECT_STORAGE,
            "signing_keys": bool(signing_key_ids),
            "encryption_key": bool(settings.TICKETING_CREDENTIAL_ENCRYPTION_KEY),
            "pending_migrations": pending_migrations,
            "storage_backend": default_storage.__class__.__name__,
            "background_jobs": bool(settings.CELERY_BROKER_URL),
            "key_error": key_error,
            "signing_key_ids": signing_key_ids,
            "verification_key_ids": verification_key_ids,
        },
        "organisations": organisations,
        "users": users,
        "events": events,
        "recent_events": events[:8],
        "recent_audit": recent_audit,
        "recent_scans": recent_scans,
        "finance": {
            "paid_orders": paid_orders.count(),
            "gross_minor": paid_orders.aggregate(total=Sum("total_minor"))["total"] or 0,
            "fees_minor": paid_orders.aggregate(total=Sum("fee_minor"))["total"] or 0,
            "refunded_count": refunded_payments.count(),
            "refunded_minor": refunded_payments.aggregate(total=Sum("amount_minor"))["total"] or 0,
            "payouts_pending": Payout.objects.filter(status=Payout.Status.PENDING).count(),
            "payouts_paid": Payout.objects.filter(status=Payout.Status.PAID).count(),
            "payouts_minor": Payout.objects.filter(status=Payout.Status.PAID).aggregate(total=Sum("amount_minor"))["total"] or 0,
            "ledger_transactions": LedgerEntry.objects.values("transaction_id").distinct().count(),
            "commission_rate": PlatformCommissionConfig.current().commission_rate,
            "commission_minor": CommissionTransaction.objects.aggregate(total=Sum("commission_minor"))["total"] or 0,
            "commission_by_event": CommissionTransaction.objects.values("event__name", "organisation__name").annotate(total=Sum("commission_minor")).order_by("-total")[:10],
            "commission_by_organisation": CommissionTransaction.objects.values("organisation__name").annotate(total=Sum("commission_minor")).order_by("-total")[:10],
        },
    }
    return render(request, "dashboard/platform.html", context)


@platform_owner_required
@require_POST
def platform_user_toggle(request, user_id):
    from accounts.models import User
    from audit.models import AuditLog

    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot suspend your own platform owner account.")
        return redirect("platform-dashboard")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    AuditLog.objects.create(
        actor=request.user,
        action="platform_user_activated" if target.is_active else "platform_user_suspended",
        object_id=str(target.pk),
        metadata={"email": target.email},
    )
    messages.success(request, f"{target.email} is now {'active' if target.is_active else 'suspended'}.")
    return redirect("platform-dashboard")


@platform_owner_required
@require_POST
def platform_event_action(request, event_id):
    from audit.models import AuditLog

    event = get_object_or_404(Event, pk=event_id)
    action = request.POST.get("action")
    if action == "suspend" and event.status not in {Event.Status.CANCELLED, Event.Status.COMPLETED}:
        event.status = Event.Status.SALES_PAUSED
        message = "Event sales paused."
    elif action == "activate" and event.status == Event.Status.SALES_PAUSED:
        event.status = Event.Status.SALES_OPEN
        message = "Event sales reopened."
    elif action == "cancel" and event.status not in {Event.Status.CANCELLED, Event.Status.COMPLETED}:
        event.status = Event.Status.CANCELLED
        message = "Event cancelled."
    else:
        messages.error(request, "That event transition is not available.")
        return redirect("platform-dashboard")
    event.save(update_fields=["status", "updated_at"])
    AuditLog.objects.create(actor=request.user, action=f"platform_event_{action}", object_id=str(event.pk), metadata={"event": event.name})
    messages.success(request, message)
    return redirect("platform-dashboard")


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
            event.starting_price_minor
            if event.starting_price_minor is not None
            else None
        )
    return events


def _with_public_availability(events):
    events = list(events)
    for event in events:
        categories = list(event.ticket_categories.all())
        event.has_ticket_categories = bool(categories)
        event.available_ticket_count = sum(category.available_count for category in categories)
        event.has_available_tickets = event.available_ticket_count > 0
    return events


def public_home(request):
    events = _with_public_availability(_public_events())
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
    ticketing_model = request.GET.get("ticketing_model", "").strip()
    availability = request.GET.get("availability", "").strip()
    sort = request.GET.get("sort", "soonest").strip()
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
    if ticketing_model in {Event.TicketingModel.GENERAL_ADMISSION, Event.TicketingModel.RESERVED_SEATING}:
        events = events.filter(ticketing_model=ticketing_model)
    try:
        if date_from:
            events = events.filter(starts_at__date__gte=date.fromisoformat(date_from))
        if date_to:
            events = events.filter(starts_at__date__lte=date.fromisoformat(date_to))
    except ValueError:
        messages.warning(request, "Use valid dates to filter events.")
        date_from = ""
        date_to = ""
    if sort == "latest":
        events = events.order_by("-starts_at")
    else:
        sort = "soonest"
        events = events.order_by("starts_at")
    events = _with_public_availability(events.distinct())
    if availability == "available":
        events = [event for event in events if event.has_available_tickets]
    elif availability == "sold_out":
        events = [event for event in events if not event.has_available_tickets]
    else:
        availability = ""
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
            "events": events,
            "query": query,
            "category": category,
            "location": location,
            "date_from": date_from,
            "date_to": date_to,
            "ticketing_model": ticketing_model,
            "availability": availability,
            "sort": sort,
            "categories": categories,
        },
    )


def public_event_detail(request, pk):
    event = get_object_or_404(
        _public_events().prefetch_related(
            "ticket_categories__section_pricing__section",
        ),
        pk=pk,
    )
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
        "metrics": {"revenue_minor": revenue, "revenue_maloti": revenue, "tickets_sold": sold, "tickets_available": available, "check_ins": checked_in, "active_events": events.filter(status__in=[Event.Status.PUBLISHED, Event.Status.SALES_OPEN]).count(), "pending_payments": pending_payments.count()},
        "recent_orders": Order.objects.filter(event_id__in=event_ids).select_related("event", "customer")[:6],
    }
    return render(request, "dashboard/home.html", context)


@organiser_required
def event_attendee_export(request, event_id):
    event = get_object_or_404(
        Event.objects.filter(organisation__memberships__user=request.user),
        pk=event_id,
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="event-{event.pk}-attendees.csv"'
    writer = csv.writer(response)
    writer.writerow(["ticket_reference", "attendee_name", "owner_email", "ticket_status", "seat", "admitted_at", "gate", "scanner_device"])
    tickets = Ticket.objects.filter(event=event).select_related("owner", "admission__device").order_by("reference")
    for ticket in tickets.iterator():
        admission = getattr(ticket, "admission", None)
        writer.writerow([
            ticket.reference,
            ticket.attendee_name,
            ticket.owner.email,
            ticket.status,
            ticket.seat_label,
            admission.admitted_at.isoformat() if admission else "",
            admission.gate if admission else "",
            admission.device.device_id if admission and admission.device else "",
        ])
    return response


@payment_reviewer_required
def pending_payments(request):
    """Show organiser-scoped orders awaiting payment confirmation."""
    from orders.models import Order

    query = request.GET.get("q", "").strip()
    orders = (
        Order.objects.filter(
            event__organisation__memberships__user=request.user,
            status=Order.Status.PENDING,
        )
        .select_related("event", "customer")
        .prefetch_related("payments")
        .order_by("created_at")
    )
    if query:
        orders = orders.filter(
            Q(reference__icontains=query) | Q(payments__provider_reference__icontains=query)
        ).distinct()
    return render(request, "dashboard/pending_payments.html", {"orders": orders, "query": query})


@payment_reviewer_required
def event_pending_payments(request, event_id):
    from orders.models import Order

    event = get_object_or_404(
        Event.objects.filter(organisation__memberships__user=request.user), pk=event_id
    )
    query = request.GET.get("q", "").strip()
    orders = Order.objects.filter(event=event, status=Order.Status.PENDING).select_related(
        "event", "customer"
    ).prefetch_related("payments").order_by("created_at")
    if query:
        orders = orders.filter(
            Q(reference__icontains=query) | Q(payments__provider_reference__icontains=query)
        ).distinct()
    return render(request, "dashboard/pending_payments.html", {"orders": orders, "query": query, "event": event})


@payment_reviewer_required
def review_payment(request, payment_id):
    if request.method != "POST":
        return redirect("pending-payments")
    payment = get_object_or_404(
        Payment.objects.select_related("order__event__organisation", "payment_method"),
        pk=payment_id,
        order__event__organisation__memberships__user=request.user,
    )
    form = PaymentReviewForm(request.POST)
    if not form.is_valid():
        errors = "; ".join(
            error
            for field_errors in form.errors.values()
            for error in field_errors
        )
        messages.error(request, f"Payment review could not be saved: {errors}")
        return redirect("pending-payments")
    note = form.cleaned_data["review_note"].strip()
    decision = form.cleaned_data["decision"]
    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
            if payment.status not in {Payment.Status.PENDING, Payment.Status.INITIATED}:
                raise ValueError("This payment has already been reviewed.")
            previous_status = payment.status
            received_amount_minor = None
            if form.cleaned_data.get("received_amount_maloti") is not None:
                received_amount_minor = form.cleaned_data["received_amount_maloti"]
            if decision == "approve":
                confirm_payment(
                    payment_id=payment.pk,
                    provider_reference=payment.provider_reference,
                    response={"method": "manual_review", "note": note},
                    received_amount_minor=received_amount_minor,
                )
                message = "Payment approved and tickets issued."
                resulting_status = Payment.Status.SUCCESSFUL
            else:
                payment.mark_failed(reason=note or "Rejected during manual review")
                payment.order.status = payment.order.Status.FAILED
                payment.order.save(update_fields=["status", "updated_at"])
                payment.order.inventory_holds.filter(status="active").update(
                    status="released", updated_at=timezone.now()
                )
                message = "Payment rejected and the order was marked failed."
                resulting_status = Payment.Status.FAILED
            payment.reviewed_at = timezone.now()
            payment.reviewed_by = request.user
            payment.review_note = note
            payment.save(update_fields=["reviewed_at", "reviewed_by", "review_note", "updated_at"])
            PaymentReview.objects.create(
                payment=payment,
                reviewer=request.user,
                decision=PaymentReview.Decision.APPROVED if decision == "approve" else PaymentReview.Decision.REJECTED,
                previous_status=previous_status,
                resulting_status=resulting_status,
                received_amount_minor=received_amount_minor,
                note=note,
            )
            from audit.services import record
            record(action=f"payment_{decision}", actor=request.user, obj=payment, metadata={"order": payment.order.reference, "note": note})
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, message)
    return redirect("pending-payments")


@payment_reviewer_required
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


@customer_required
@require_POST
def request_order_refund(request, order_id):
    amount = request.POST.get("amount_maloti", "")
    try:
        refund = create_refund_request(
            order_id=order_id,
            requester=request.user,
            amount_minor=amount,
            reason=request.POST.get("reason", ""),
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Refund request {refund.id} was submitted for review.")
    return redirect("orders:order-detail", pk=order_id)


@customer_required
def customer_refunds(request):
    from payments.models import RefundRequest

    refunds = RefundRequest.objects.filter(requester=request.user).select_related("order__event")
    return render(request, "dashboard/customer_refunds.html", {"refunds": refunds})


@payment_reviewer_required
def organiser_refunds(request):
    from payments.models import RefundRequest

    refunds = RefundRequest.objects.all()
    if not (request.user.is_staff or request.user.is_superuser):
        refunds = refunds.filter(order__event__organisation__memberships__user=request.user)
    refunds = refunds.select_related("order__event", "requester", "reviewer", "executor")
    return render(request, "dashboard/organiser_refunds.html", {"refunds": refunds})


@payment_reviewer_required
def event_organiser_refunds(request, event_id):
    from payments.models import RefundRequest

    event = get_object_or_404(
        Event.objects.filter(organisation__memberships__user=request.user), pk=event_id
    )
    refunds = RefundRequest.objects.filter(order__event=event).select_related(
        "order__event", "requester", "reviewer", "executor"
    )
    return render(request, "dashboard/organiser_refunds.html", {"refunds": refunds, "event": event})


@payment_reviewer_required
@require_POST
def organiser_refund_review(request, refund_id):
    try:
        amount = request.POST.get("approved_amount_maloti") or None
        refund = review_refund(
            refund_id=refund_id,
            reviewer=request.user,
            decision=request.POST.get("decision", ""),
            approved_amount_minor=amount,
            note=request.POST.get("review_note", ""),
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Refund {refund.id} is now {refund.get_status_display().lower()}.")
    return redirect("organiser-refunds")


@payment_reviewer_required
@require_POST
def organiser_refund_start(request, refund_id):
    try:
        refund = start_refund_processing(
            refund_id=refund_id,
            actor=request.user,
            note=request.POST.get("execution_note", ""),
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Refund {refund.id} is awaiting verified execution.")
    return redirect("organiser-refunds")


@payment_reviewer_required
@require_POST
def organiser_refund_complete(request, refund_id):
    try:
        refund = complete_refund(
            refund_id=refund_id,
            actor=request.user,
            provider_reference=request.POST.get("provider_reference", ""),
            note=request.POST.get("execution_note", ""),
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Refund {refund.id} was recorded as completed.")
    return redirect("organiser-refunds")


@payment_reviewer_required
@require_POST
def organiser_refund_fail(request, refund_id):
    try:
        refund = fail_refund(
            refund_id=refund_id,
            actor=request.user,
            note=request.POST.get("execution_note", ""),
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.error(request, f"Refund {refund.id} requires intervention.")
    return redirect("organiser-refunds")
