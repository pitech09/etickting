from decimal import Decimal

from django import forms

from seating.models import SeatingRow
from venues.models import Venue

from .models import Event, Ticket, TicketCategory


class TicketAttendeeForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("attendee_name", "attendee_photo")
        widgets = {"attendee_photo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"})}

    def clean_attendee_photo(self):
        photo = self.cleaned_data.get("attendee_photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Photo must be 5 MB or smaller.")
        return photo


class EventForm(forms.ModelForm):
    venue_name = forms.CharField(max_length=200, label="Venue name")
    venue_address_line_1 = forms.CharField(max_length=200, label="Address")
    venue_address_line_2 = forms.CharField(max_length=200, required=False, label="Address line 2")
    venue_city = forms.CharField(max_length=100, label="City or town")
    ticket_name = forms.CharField(max_length=100, label="Ticket name", initial="General admission")
    ticket_price_maloti = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.00"), label="Ticket price (M)")
    ticket_quantity = forms.IntegerField(min_value=1, label="Tickets available")
    ticket_max_per_customer = forms.IntegerField(min_value=1, initial=10, label="Max per customer")
    seating_rows = forms.IntegerField(
        min_value=1,
        max_value=200,
        required=False,
        initial=3,
        label="Seating rows",
        help_text="For example, 3 rows.",
    )
    seats_per_row = forms.IntegerField(
        min_value=1,
        max_value=500,
        required=False,
        initial=4,
        label="Seats per row",
        help_text="For example, 4 seats per row.",
    )

    class Meta:
        model = Event
        fields = (
            "name",
            "description",
            "cover_image",
            "starts_at",
            "ends_at",
            "sales_opens_at",
            "sales_closes_at",
            "timezone",
            "ticketing_model",
            "admission_policy",
            "refund_policy",
            "resale_policy",
            "status",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "sales_opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "sales_closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "refund_policy": forms.Textarea(attrs={"rows": 3}),
            "resale_policy": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, organisation=None, **kwargs):
        creating = kwargs.pop("creating", False)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.venue_id:
            venue = self.instance.venue
            self.initial.update({
                "venue_name": venue.name,
                "venue_address_line_1": venue.address_line_1,
                "venue_address_line_2": venue.address_line_2,
                "venue_city": venue.city,
            })
        category = self.instance.ticket_categories.order_by("created_at").first() if self.instance and self.instance.pk else None
        if category:
            self.initial.update({
                "ticket_name": category.name,
                "ticket_price_maloti": Decimal(category.price_minor) / Decimal("100"),
                "ticket_quantity": category.total_quantity,
                "ticket_max_per_customer": category.max_per_customer,
            })
        if self.instance and self.instance.pk and self.instance.ticketing_model == Event.TicketingModel.RESERVED_SEATING:
            try:
                rows = list(SeatingRow.objects.filter(section__venue=self.instance.event_seating.venue))
            except (AttributeError, SeatingRow.DoesNotExist):
                rows = []
            if rows:
                self.initial.update({
                    "seating_rows": len(rows),
                    "seats_per_row": max(row.seats.count() for row in rows),
                })
        self.creating = creating

    def clean_venue_name(self):
        return self.cleaned_data["venue_name"].strip()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("ticketing_model") == Event.TicketingModel.RESERVED_SEATING:
            rows = cleaned_data.get("seating_rows")
            seats_per_row = cleaned_data.get("seats_per_row")
            if rows and seats_per_row:
                cleaned_data["ticket_quantity"] = rows * seats_per_row
        return cleaned_data


class TicketCategoryForm(forms.ModelForm):
    price_maloti = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        label="Price (M)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["price_maloti"] = Decimal(self.instance.price_minor) / Decimal("100")

    class Meta:
        model = TicketCategory
        fields = (
            "name",
            "description",
            "price_maloti",
            "total_quantity",
            "max_per_customer",
            "sales_opens_at",
            "sales_closes_at",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "sales_opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "sales_closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "price_maloti": forms.NumberInput(attrs={"placeholder": "0.00", "min": "0", "step": "0.01"}),
            "total_quantity": forms.NumberInput(attrs={"placeholder": "0", "min": "0"}),
            "max_per_customer": forms.NumberInput(attrs={"placeholder": "10", "min": "1"}),
        }

    def clean_total_quantity(self):
        quantity = self.cleaned_data.get("total_quantity")
        if quantity is not None and quantity < 1:
            raise forms.ValidationError("Total quantity must be at least 1.")
        return quantity

    def clean_max_per_customer(self):
        limit = self.cleaned_data.get("max_per_customer")
        if limit is not None and limit < 1:
            raise forms.ValidationError("Max per customer must be at least 1.")
        return limit
