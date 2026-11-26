from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from organisations.models import OrganisationMembership

from .forms import PlatformCommissionForm
from .models import CommissionTransaction, FinancialTransaction, LedgerEntry, Payout, PlatformCommissionConfig
from .services import organisation_earnings


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
