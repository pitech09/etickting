from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from organisations.models import OrganisationMembership

from .models import FinancialTransaction, LedgerEntry, Payout
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
