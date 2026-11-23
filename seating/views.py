from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organisations.models import OrganisationMembership
from dashboard.views import customer_required

from .models import EventSeating, SeatingRow, SeatingSection, Seat, SeatReservation
from .services import (
    convert_reservation_to_allocation,
    get_event_seat_availability,
    reserve_seats,
)


class _RequiresOrganisationEventAccess(LoginRequiredMixin):
    """Mixin that enforces organisation membership before acting on an event."""

    def dispatch(self, request, *args, **kwargs):
        event_id = kwargs.get("pk") or kwargs.get("event_id")
        if event_id:
            from ticketing.models import Event

            organisation_id = (
                Event.objects.filter(pk=event_id)
                .values_list("organisation_id", flat=True)
                .first()
            )
            if organisation_id:
                if not OrganisationMembership.objects.filter(
                    organisation_id=organisation_id, user=request.user
                ).exists():
                    raise PermissionDenied(
                        "You do not belong to this organisation."
                    )
        return super().dispatch(request, *args, **kwargs)


class SeatingSectionListView(_RequiresOrganisationEventAccess, ListView):
    model = SeatingSection
    template_name = "seating/section_list.html"
    context_object_name = "sections"

    def get_queryset(self):
        venue_id = self.kwargs.get("venue_id")
        return SeatingSection.objects.filter(venue_id=venue_id).order_by(
            "sort_order", "name"
        )


class SeatingSectionCreateView(_RequiresOrganisationEventAccess, CreateView):
    model = SeatingSection
    fields = ("name", "description", "color", "price_modifier_minor", "is_accessible", "sort_order")
    template_name = "seating/section_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["venue"] = get_object_or_404(
            __import__("venues.models", fromlist=["Venue"]).Venue,
            pk=self.kwargs.get("venue_id"),
        )
        return context

    def form_valid(self, form):
        form.instance.venue_id = self.kwargs.get("venue_id")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "seating:section-list", kwargs={"venue_id": self.kwargs.get("venue_id")}
        )


class SeatingRowListView(_RequiresOrganisationEventAccess, ListView):
    model = SeatingRow
    template_name = "seating/row_list.html"
    context_object_name = "rows"

    def get_queryset(self):
        return SeatingRow.objects.filter(
            section_id=self.kwargs.get("section_id")
        ).order_by("sort_order", "name")


class SeatingRowCreateView(_RequiresOrganisationEventAccess, CreateView):
    model = SeatingRow
    fields = ("name", "sort_order")
    template_name = "seating/row_form.html"

    def form_valid(self, form):
        form.instance.section_id = self.kwargs.get("section_id")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "seating:row-list", kwargs={"section_id": self.kwargs.get("section_id")}
        )


@login_required
@require_POST
def generate_seats(request, row_id):
    """Generate numbered seats for a row."""
    from django.contrib import messages

    row = get_object_or_404(SeatingRow, pk=row_id)
    start = int(request.POST.get("start_number", 1))
    count = int(request.POST.get("count", 1))

    created = []
    with transaction.atomic():
        for i in range(count):
            number = str(start + i)
            label = f"{row.section.name} {row.name}-{number}"
            seat, _ = Seat.objects.update_or_create(
                row=row,
                number=number,
                defaults={"label": label, "sort_order": start + i},
            )
            created.append(seat)

    messages.success(request, f"Generated {len(created)} seats for row {row.name}.")
    return redirect("seating:seat-list", row_id=row.id)


@login_required
def seat_list(request, row_id):
    row = get_object_or_404(SeatingRow, pk=row_id)
    seats = Seat.objects.filter(row=row).order_by("sort_order", "number")
    return render(request, "seating/seat_list.html", {"row": row, "seats": seats})


class SeatUpdateView(_RequiresOrganisationEventAccess, UpdateView):
    model = Seat
    fields = ("number", "label", "status", "is_accessible", "is_restricted_view", "sort_order")
    template_name = "seating/seat_form.html"

    def get_success_url(self):
        return reverse(
            "seating:seat-list", kwargs={"row_id": self.object.row_id}
        )


@customer_required
@require_GET
def event_seating_map(request, event_id):
    """Customer-facing seating map for seat selection."""
    from ticketing.models import Event

    event = get_object_or_404(Event, pk=event_id, status__in=["published", "sales_open"])
    if not event.sales_are_open():
        return redirect("public-event-detail", pk=event.pk)
    try:
        event_seating = event.event_seating
    except AttributeError:
        return render(
            request,
            "seating/no_seating.html",
            {"event": event},
        )

    sections = (
        SeatingSection.objects.filter(venue=event_seating.venue)
        .prefetch_related("rows__seats")
        .order_by("sort_order", "name")
    )

    # Build seat data for the map
    seat_data = []
    for section in sections:
        for row in section.rows.all():
            for seat in row.seats.all():
                seat_data.append(
                    {
                        "id": str(seat.id),
                        "section": section.name,
                        "row": row.name,
                        "number": seat.number,
                        "label": seat.label,
                        "status": seat.status,
                        "is_available": seat.is_currently_available,
                        "is_accessible": seat.is_accessible,
                        "is_restricted_view": seat.is_restricted_view,
                    }
                )

    return render(
        request,
        "seating/seating_map.html",
        {
            "event": event,
            "sections": sections,
            "seat_data": seat_data,
        },
    )


@customer_required
@require_GET
def event_seat_map(request, event_id):
    """Customer-facing seating map with real-time availability."""
    from ticketing.models import Event

    event = get_object_or_404(Event, pk=event_id, status__in=["published", "sales_open"])
    if not event.sales_are_open():
        return redirect("public-event-detail", pk=event.pk)
    try:
        event_seating = event.event_seating
    except AttributeError:
        return render(request, "seating/no_seating.html", {"event": event})

    sections = (
        SeatingSection.objects.filter(venue=event_seating.venue)
        .prefetch_related("rows__seats")
        .order_by("sort_order", "name")
    )

    seats_data = []
    for section in sections:
        for row in section.rows.all():
            for seat in row.seats.all():
                seat_info = {
                    "id": str(seat.id),
                    "label": seat.label,
                    "section": section.name,
                    "row": row.name,
                    "number": seat.number,
                    "status": seat.status,
                    "is_available": seat.status == Seat.Status.AVAILABLE,
                    "is_accessible": seat.is_accessible,
                    "is_restricted_view": seat.is_restricted_view,
                }
                active_res = seat.reservations.filter(
                    status=SeatReservation.Status.ACTIVE,
                    expires_at__gt=timezone.now(),
                ).first()
                if active_res:
                    seat_info["status"] = "reserved"
                    seat_info["is_available"] = False
                    seat_info["reservation_expires_at"] = active_res.expires_at.isoformat()
                seats_data.append(seat_info)

    availability = get_event_seat_availability(event)

    return render(
        request,
        "seating/seating_map.html",
        {
            "event": event,
            "sections": sections,
            "seat_data": seats_data,
            "availability": availability,
            "ticket_price_minor": event.ticket_categories.order_by("price_minor").values_list("price_minor", flat=True).first() or 0,
        },
    )


@customer_required
@require_POST
def reserve_customer_seats(request, event_id):
    """API endpoint to reserve seats during checkout."""
    import json

    from ticketing.models import Event

    event = get_object_or_404(Event, pk=event_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    seat_ids = data.get("seat_ids", [])
    session_key = request.session.session_key or request.session.cycle_key()

    reservations, errors = reserve_seats(
        event=event,
        seat_ids=seat_ids,
        session_key=session_key,
    )

    if errors:
        return JsonResponse({"detail": " ".join(errors)}, status=400)

    return JsonResponse(
        {
            "reserved": [
                {
                    "id": str(r.id),
                    "seat_label": r.seat.label,
                    "expires_at": r.expires_at.isoformat(),
                }
                for r in reservations
            ],
            "session_key": session_key,
        }
    )
