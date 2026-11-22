from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ticketing.models import Event


@login_required
def dashboard(request):
    memberships = request.user.organisation_memberships.select_related("organisation")
    events = Event.objects.filter(organisation__memberships__user=request.user).select_related("organisation").order_by("starts_at")
    return render(request, "dashboard/home.html", {"memberships": memberships, "events": events})
