from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organisations.models import OrganisationMembership

from .models import Venue


class _RequiresOrganisationAccess(LoginRequiredMixin):
    """Mixin that enforces organisation membership before acting on a venue."""

    def dispatch(self, request, *args, **kwargs):
        organisation_id = self._get_organisation_id(request, **kwargs)
        if organisation_id:
            if not OrganisationMembership.objects.filter(
                organisation_id=organisation_id, user=request.user
            ).exists():
                raise PermissionDenied(
                    "You do not belong to this organisation."
                )
        return super().dispatch(request, *args, **kwargs)

    def _get_organisation_id(self, request, **kwargs):
        venue_id = kwargs.get("pk")
        if venue_id:
            return (
                Venue.objects.filter(pk=venue_id)
                .values_list("organisation_id", flat=True)
                .first()
            )
        if request.method == "POST":
            return request.POST.get("organisation")
        return None


class VenueListView(_RequiresOrganisationAccess, ListView):
    model = Venue
    template_name = "venues/venue_list.html"
    context_object_name = "venues"

    def get_queryset(self):
        return (
            Venue.objects.filter(
                organisation__memberships__user=self.request.user
            )
            .select_related("organisation")
            .order_by("name")
        )


class VenueCreateView(_RequiresOrganisationAccess, CreateView):
    model = Venue
    fields = (
        "organisation",
        "name",
        "slug",
        "description",
        "address_line_1",
        "address_line_2",
        "city",
        "country",
        "capacity",
    )
    template_name = "venues/venue_form.html"
    success_url = reverse_lazy("venue-list")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        form.fields["organisation"].queryset = (
            __import__("organisations.models", fromlist=["Organisation"])
            .Organisation.objects.filter(memberships__user=user)
        )
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f'Venue "{self.object.name}" was created.'
        )
        return response


class VenueDetailView(_RequiresOrganisationAccess, DetailView):
    model = Venue
    template_name = "venues/venue_detail.html"
    context_object_name = "venue"


class VenueUpdateView(_RequiresOrganisationAccess, UpdateView):
    model = Venue
    fields = (
        "name",
        "slug",
        "description",
        "address_line_1",
        "address_line_2",
        "city",
        "country",
        "capacity",
    )
    template_name = "venues/venue_form.html"

    def get_queryset(self):
        return Venue.objects.filter(
            organisation__memberships__user=self.request.user
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f'Venue "{self.object.name}" was updated.'
        )
        return response

    def get_success_url(self):
        return reverse("venue-detail", kwargs={"pk": self.object.pk})