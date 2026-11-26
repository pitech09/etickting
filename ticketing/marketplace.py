from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import ResaleListing
from .services import create_resale_listing, purchase_resale


def listing_list(request):
    listings = ResaleListing.objects.filter(status=ResaleListing.Status.OPEN).select_related("ticket__event", "seller")
    return render(request, "ticketing/marketplace.html", {"listings": listings, "sandbox": settings.DEBUG})


@login_required
@require_POST
def listing_create(request, ticket_id):
    try:
        from decimal import Decimal, InvalidOperation
        try:
            resale_price = Decimal(request.POST.get("price", "0"))
        except InvalidOperation:
            resale_price = Decimal("0")
        create_resale_listing(ticket_id=ticket_id, seller=request.user, price_minor=resale_price)
        messages.success(request, "Your ticket is now listed for resale.")
    except (ValueError, PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    return redirect("ticketing:ticket-detail", pk=ticket_id)


@login_required
@require_POST
def listing_purchase(request, listing_id):
    listing = get_object_or_404(ResaleListing, pk=listing_id, status=ResaleListing.Status.OPEN)
    # The sandbox flag is deliberately explicit; production requires a verified provider callback.
    if not settings.DEBUG or request.POST.get("sandbox_confirm") != "1":
        messages.error(request, "Payment must be completed and verified before transfer.")
        return redirect("ticketing:marketplace")
    try:
        purchase_resale(listing_id=listing.id, buyer=request.user, payment_verified=True)
        messages.success(request, "Payment simulated in development. The ticket is now in your wallet.")
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    return redirect("ticketing:marketplace")
