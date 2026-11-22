from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.utils.text import slugify
from decimal import Decimal

from organisations.models import OrganisationMembership
from seating.models import EventSeating, Seat, SeatingRow, SeatingSection
from venues.models import Venue

from .forms import EventForm, TicketCategoryForm
from .models import Admission, Event, TicketCategory
from .services import admit_ticket, verify_credential
from .inventory import inventory_snapshot


class _RequiresOrganisationEventAccess(LoginRequiredMixin):
    """Mixin that enforces organisation membership before acting on an event."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (
            request.user.is_staff
            or request.user.is_superuser
            or OrganisationMembership.objects.filter(user=request.user).exists()
        ):
            return redirect("customer-dashboard")
        event_id = kwargs.get("pk") or kwargs.get("event_id")
        if event_id:
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


class EventListView(_RequiresOrganisationEventAccess, ListView):
    model = Event
    template_name = "ticketing/event_list.html"
    context_object_name = "events"

    def get_queryset(self):
        return (
            Event.objects.filter(
                organisation__memberships__user=self.request.user
            )
            .select_related("organisation", "venue")
            .order_by("-created_at")
        )


class EventCreateView(_RequiresOrganisationEventAccess, CreateView):
    model = Event
    form_class = EventForm
    template_name = "ticketing/event_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organisation"] = self._user_organisation()
        kwargs["creating"] = True
        return kwargs

    def _user_organisation(self):
        membership = (
            OrganisationMembership.objects.filter(user=self.request.user)
            .select_related("organisation")
            .first()
        )
        return membership.organisation if membership else None

    def form_valid(self, form):
        organisation = self._user_organisation()
        form.instance.organisation = organisation
        with transaction.atomic():
            venue = self._save_venue(form, organisation)
            form.instance.venue = venue
            response = super().form_valid(form)
            self._save_ticket_category(form)
            self._ensure_reserved_seating(form)
        messages.success(
            self.request, f'Event "{self.object.name}" was created as a draft.'
        )
        return response

    def _save_ticket_category(self, form):
        TicketCategory.objects.create(
            event=self.object,
            name=form.cleaned_data["ticket_name"],
            price_minor=int(form.cleaned_data["ticket_price_maloti"] * Decimal("100")),
            total_quantity=form.cleaned_data["ticket_quantity"],
            max_per_customer=form.cleaned_data["ticket_max_per_customer"],
        )

    def _save_venue(self, form, organisation):
        venue = form.instance.venue
        if venue is None:
            base_slug = slugify(form.cleaned_data["venue_name"]) or "venue"
            slug = base_slug
            suffix = 2
            while Venue.objects.filter(organisation=organisation, slug=slug).exists():
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            venue = Venue(organisation=organisation, slug=slug)
        venue.name = form.cleaned_data["venue_name"]
        venue.address_line_1 = form.cleaned_data["venue_address_line_1"]
        venue.address_line_2 = form.cleaned_data["venue_address_line_2"]
        venue.city = form.cleaned_data["venue_city"]
        venue.save()
        return venue

    def _ensure_reserved_seating(self, form):
        if form.cleaned_data["ticketing_model"] != Event.TicketingModel.RESERVED_SEATING:
            return

        event = self.object
        event_seating, _ = EventSeating.objects.get_or_create(
            event=event,
            defaults={"venue": event.venue},
        )
        if event_seating.venue_id != event.venue_id:
            event_seating.venue = event.venue
            event_seating.save(update_fields=["venue", "updated_at"])

        if Seat.objects.filter(row__section__venue=event_seating.venue).exists():
            return

        quantity = form.cleaned_data["ticket_quantity"]
        row_count = form.cleaned_data.get("seating_rows")
        seats_per_row = form.cleaned_data.get("seats_per_row")
        if not row_count or not seats_per_row:
            seats_per_row = 10
            row_count = (quantity + seats_per_row - 1) // seats_per_row
        section = SeatingSection.objects.create(
            venue=event_seating.venue,
            name="Main floor",
            sort_order=0,
        )
        for row_index in range(row_count):
            row_name = chr(ord("A") + row_index) if row_index < 26 else str(row_index + 1)
            row = SeatingRow.objects.create(
                section=section,
                name=row_name,
                sort_order=row_index,
            )
            remaining = min(seats_per_row, quantity - (row_index * seats_per_row))
            Seat.objects.bulk_create([
                Seat(
                    row=row,
                    number=str(seat_number),
                    label=f"{row_name}-{seat_number}",
                    sort_order=seat_number,
                )
                for seat_number in range(1, remaining + 1)
            ])

    def get_success_url(self):
        return reverse("ticketing:event-detail", kwargs={"pk": self.object.pk})


class EventDetailView(_RequiresOrganisationEventAccess, DetailView):
    model = Event
    template_name = "ticketing/event_detail.html"
    context_object_name = "event"


class EventUpdateView(_RequiresOrganisationEventAccess, UpdateView):
    model = Event
    form_class = EventForm
    template_name = "ticketing/event_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organisation"] = self.object.organisation
        return kwargs

    def get_queryset(self):
        return Event.objects.filter(
            organisation__memberships__user=self.request.user
        )

    def form_valid(self, form):
        venue = self.object.venue
        if venue is None:
            organisation = self.object.organisation
            base_slug = slugify(form.cleaned_data["venue_name"]) or "venue"
            slug = base_slug
            suffix = 2
            while Venue.objects.filter(organisation=organisation, slug=slug).exists():
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            venue = Venue(organisation=organisation, slug=slug)
        venue.name = form.cleaned_data["venue_name"]
        venue.address_line_1 = form.cleaned_data["venue_address_line_1"]
        venue.address_line_2 = form.cleaned_data["venue_address_line_2"]
        venue.city = form.cleaned_data["venue_city"]
        with transaction.atomic():
            venue.save()
            response = super().form_valid(form)
            category = self.object.ticket_categories.order_by("created_at").first()
            if category:
                category.name = form.cleaned_data["ticket_name"]
                category.price_minor = int(form.cleaned_data["ticket_price_maloti"] * Decimal("100"))
                category.total_quantity = form.cleaned_data["ticket_quantity"]
                category.max_per_customer = form.cleaned_data["ticket_max_per_customer"]
                category.save(update_fields=["name", "price_minor", "total_quantity", "max_per_customer", "updated_at"])
            else:
                TicketCategory.objects.create(
                    event=self.object,
                    name=form.cleaned_data["ticket_name"],
                    price_minor=int(form.cleaned_data["ticket_price_maloti"] * Decimal("100")),
                    total_quantity=form.cleaned_data["ticket_quantity"],
                    max_per_customer=form.cleaned_data["ticket_max_per_customer"],
                )
            self._ensure_reserved_seating(form)
        messages.success(
            self.request, f'Event "{self.object.name}" was updated.'
        )
        return response

    def _ensure_reserved_seating(self, form):
        if form.cleaned_data["ticketing_model"] != Event.TicketingModel.RESERVED_SEATING:
            return

        event = self.object
        event_seating, _ = EventSeating.objects.get_or_create(
            event=event,
            defaults={"venue": event.venue},
        )
        if event_seating.venue_id != event.venue_id:
            event_seating.venue = event.venue
            event_seating.save(update_fields=["venue", "updated_at"])

    def get_success_url(self):
        return reverse("ticketing:event-detail", kwargs={"pk": self.object.pk})


class EventPublishView(_RequiresOrganisationEventAccess, View):
    @transaction.atomic
    def post(self, request, pk):
        event = get_object_or_404(
            Event.objects.filter(
                organisation__memberships__user=request.user
            ),
            pk=pk,
        )
        if not event.can_publish():
            messages.error(
                request,
                "This event cannot be published yet. Make sure it has a name and start date.",
            )
            return redirect("ticketing:event-detail", pk=event.pk)
        event.status = Event.Status.PUBLISHED
        event.save(update_fields=["status", "updated_at"])
        messages.success(
            request, f'Event "{event.name}" is now published.'
        )
        return redirect("ticketing:event-detail", pk=event.pk)


class EventSalesOpenView(_RequiresOrganisationEventAccess, View):
    @transaction.atomic
    def post(self, request, pk):
        event = get_object_or_404(
            Event.objects.filter(
                organisation__memberships__user=request.user
            ),
            pk=pk,
        )
        if event.status != Event.Status.PUBLISHED:
            messages.error(
                request, "Only published events can open for sales."
            )
            return redirect("ticketing:event-detail", pk=event.pk)
        event.status = Event.Status.SALES_OPEN
        if not event.sales_opens_at:
            event.sales_opens_at = timezone.now()
        event.save(update_fields=["status", "sales_opens_at", "updated_at"])
        messages.success(
            request, f'Ticket sales are now open for "{event.name}".'
        )
        return redirect("ticketing:event-detail", pk=event.pk)


class TicketCategoryListView(_RequiresOrganisationEventAccess, ListView):
    model = TicketCategory
    template_name = "ticketing/ticket_category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        self.event = get_object_or_404(
            Event.objects.filter(
                organisation__memberships__user=self.request.user
            ),
            pk=self.kwargs["event_id"],
        )
        return (
            TicketCategory.objects.filter(event=self.event)
            .select_related("event")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.event
        return context


class TicketCategoryCreateView(_RequiresOrganisationEventAccess, CreateView):
    model = TicketCategory
    form_class = TicketCategoryForm
    template_name = "ticketing/ticket_category_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(
            Event.objects.filter(
                organisation__memberships__user=request.user
            ),
            pk=kwargs["event_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.event = self.event
        form.instance.price_minor = int(form.cleaned_data["price_maloti"] * Decimal("100"))
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Ticket category "{self.object.name}" was created.',
        )
        return response

    def get_success_url(self):
        return reverse(
            "ticketing:ticket-category-list",
            kwargs={"event_id": self.event.pk},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.event
        return context


class TicketCategoryUpdateView(_RequiresOrganisationEventAccess, UpdateView):
    model = TicketCategory
    form_class = TicketCategoryForm
    template_name = "ticketing/ticket_category_form.html"

    def get_queryset(self):
        return TicketCategory.objects.filter(
            event__organisation__memberships__user=self.request.user
        )

    def form_valid(self, form):
        form.instance.price_minor = int(form.cleaned_data["price_maloti"] * Decimal("100"))
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Ticket category "{self.object.name}" was updated.',
        )
        return response

    def get_success_url(self):
        return reverse(
            "ticketing:ticket-category-list",
            kwargs={"event_id": self.object.event.pk},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.object.event
        return context


class TicketCategoryDeleteView(_RequiresOrganisationEventAccess, DeleteView):
    model = TicketCategory
    template_name = "ticketing/ticket_category_confirm_delete.html"

    def get_queryset(self):
        return TicketCategory.objects.filter(
            event__organisation__memberships__user=self.request.user
        )

    def get_success_url(self):
        return reverse(
            "ticketing:ticket-category-list",
            kwargs={"event_id": self.object.event.pk},
        )

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(
                self.request,
                f'Ticket category "{self.object.name}" was deleted.',
            )
            return redirect(
                "ticketing:ticket-category-list", event_id=self.object.event.pk
            )
        except Exception as exc:
            from django.db.models.deletion import ProtectedError

            if isinstance(exc, ProtectedError):
                self.object.is_active = False
                self.object.save(update_fields=["is_active", "updated_at"])
                messages.warning(
                    self.request,
                    f'Ticket category "{self.object.name}" has existing references '
                    f'and could not be deleted. It has been deactivated instead.',
                )
                return redirect(
                    "ticketing:ticket-category-list", event_id=self.object.event.pk
                )
            raise


class InventoryDashboardView(_RequiresOrganisationEventAccess, DetailView):
    model = Event
    template_name = "ticketing/inventory_dashboard.html"
    context_object_name = "event"

    def get_queryset(self):
        return Event.objects.filter(organisation__memberships__user=self.request.user).select_related("organisation")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["snapshot"] = inventory_snapshot(self.object)
        return context


@login_required
@require_GET
def inventory_data(request, event_id):
    event = get_object_or_404(Event, pk=event_id, organisation__memberships__user=request.user)
    return JsonResponse(inventory_snapshot(event))


from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organisations.models import OrganisationMembership

from .forms import EventForm
from .models import Admission, Event, Ticket
from .services import admit_ticket, verify_credential


def _public_ticket(ticket, result):
    if not ticket:
        return {"authentic": False, "status": result}
    return {
        "authentic": result == "valid",
        "status": result,
        "event": ticket.event.name,
        "ticket_reference": ticket.reference,
        "seat": ticket.seat_label or None,
    }


@require_GET
def public_verify_page(request):
    return render(request, "ticketing/verify.html")


@login_required
@require_GET
def scanner_page(request, event_id):
    event = get_object_or_404(Event, pk=event_id, organisation__memberships__user=request.user)
    devices = event.scanner_devices.filter(user=request.user, active=True)
    return render(request, "ticketing/scanner.html", {"event": event, "devices": devices})


@require_GET
def public_verify(request):
    credential = request.GET.get("credential", "")
    key = f"ticket-verify:{request.META.get('REMOTE_ADDR', 'unknown')}"
    count = cache.get(key, 0)
    if count >= settings.TICKETING_PUBLIC_VERIFY_RATE_LIMIT:
        return JsonResponse({"detail": "Too many verification attempts"}, status=429)
    cache.set(key, count + 1, 60)
    ticket, result = verify_credential(credential)
    return JsonResponse(_public_ticket(ticket, result))


@login_required
@require_POST
def scan(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    rate_key = f"ticket-scan:{request.user.pk}:{request.headers.get('X-Scanner-Device', '')}"
    attempts = cache.get(rate_key, 0)
    if attempts >= settings.TICKETING_SCAN_RATE_LIMIT:
        return JsonResponse({"detail": "Too many scan attempts"}, status=429)
    cache.set(rate_key, attempts + 1, 60)
    ticket, result = admit_ticket(credential=request.POST.get("credential", ""), event=event, user=request.user, device_id=request.headers.get("X-Scanner-Device"))
    status = 200 if result in {"valid", "reentry", "used", "cancelled", "refunded", "transferred", "revoked"} else 403 if result == "unauthorised" else 400
    return JsonResponse({**_public_ticket(ticket, result), "attendee_name": ticket.attendee_name if ticket and result == "valid" else None}, status=status)
