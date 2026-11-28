import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from organisations.models import OrganisationMembership, OrganisationPaymentMethod
from ticketing.models import Event

from .forms import PlatformCommissionForm
from .models import CommissionTransaction, FinancialTransaction, LedgerEntry, Payout, PlatformCommissionConfig
from .services import organisation_earnings
from .services import create_payout


@login_required
def report(request, organisation_id):
    membership = get_object_or_404(OrganisationMembership, organisation_id=organisation_id, user=request.user)
    transactions = FinancialTransaction.objects.filter(organisation=membership.organisation).prefetch_related("entries").order_by("-created_at")
    totals = LedgerEntry.objects.filter(transaction__organisation=membership.organisation).aggregate(debits=Sum("debit_minor"), credits=Sum("credit_minor"))
    earnings = organisation_earnings(organisation=membership.organisation)
    data = {
        "organisation": membership.organisation.name,
        "debits_minor": totals["debits"] or 0,
        "credits_minor": totals["credits"] or 0,
        "earnings": earnings,
        "payouts": Payout.objects.filter(organisation=membership.organisation).order_by("-created_at"),
        "transactions": [{"reference": tx.reference, "description": tx.description, "created_at": tx.created_at.isoformat()} for tx in transactions],
    }
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(data)
    return render(request, "finance/report.html", data)


def _event_manager_membership(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.user.is_staff or request.user.is_superuser:
        return event, None
    membership = get_object_or_404(
        OrganisationMembership,
        organisation=event.organisation,
        user=request.user,
        role__in=[OrganisationMembership.Role.OWNER, OrganisationMembership.Role.EVENT_MANAGER],
    )
    return event, membership


@login_required
def event_report(request, event_id):
    event, _membership = _event_manager_membership(request, event_id)
    transactions = FinancialTransaction.objects.filter(
        organisation=event.organisation
    ).prefetch_related("entries").order_by("-created_at")
    earnings = organisation_earnings(organisation=event.organisation, event=event)
    return render(request, "finance/report.html", {
        "organisation": event.organisation.name,
        "event": event,
        "earnings": earnings,
        "payouts": Payout.objects.filter(organisation=event.organisation, event=event).order_by("-created_at"),
        "transactions": [{"reference": tx.reference, "description": tx.description, "created_at": tx.created_at.isoformat()} for tx in transactions],
        "payment_methods": OrganisationPaymentMethod.objects.filter(organisation=event.organisation, is_active=True),
        "request_key": uuid.uuid4().hex,
    })


@login_required
@require_POST
def request_event_payout(request, event_id):
    event, _membership = _event_manager_membership(request, event_id)
    payment_method = None
    method_id = request.POST.get("payment_method")
    if method_id:
        payment_method = get_object_or_404(
            OrganisationPaymentMethod,
            pk=method_id,
            organisation=event.organisation,
            is_active=True,
        )
    request_key = request.POST.get("request_key", "").strip() or uuid.uuid4().hex
    try:
        payout = create_payout(
            organisation=event.organisation,
            event=event,
            amount_minor=request.POST.get("amount_maloti", ""),
            payment_method=payment_method,
            requested_by=request.user,
            request_note=request.POST.get("request_note", ""),
            idempotency_key=f"event-payout:{event.pk}:{request_key}",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Settlement request for M {payout.amount_minor:.2f} was recorded. Provider confirmation is still required.")
    return redirect("finance:event-report", event_id=event.pk)


@login_required
@require_http_methods(["GET", "POST"])
def commission_settings(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    config = PlatformCommissionConfig.current()
    if request.method == "POST":
        form = PlatformCommissionForm(request.POST, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.updated_by = request.user
            config.save()
            return redirect("platform-dashboard")
    else:
        form = PlatformCommissionForm(instance=config)
    return render(request, "finance/commission_settings.html", {"form": form, "config": config})
