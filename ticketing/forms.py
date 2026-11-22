from django import forms

from venues.models import Venue

from .models import Event, TicketCategory


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            "name",
            "description",
            "cover_image",
            "venue",
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
        super().__init__(*args, **kwargs)
        if organisation is not None:
            self.fields["venue"].queryset = Venue.objects.filter(
                organisation=organisation
            )


class TicketCategoryForm(forms.ModelForm):
    class Meta:
        model = TicketCategory
        fields = (
            "name",
            "description",
            "price_minor",
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
            "price_minor": forms.NumberInput(
                attrs={"placeholder": "0", "min": "0"}
            ),
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