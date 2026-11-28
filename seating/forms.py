from decimal import Decimal

from django import forms

from .models import SeatingSection


class SeatingSectionForm(forms.ModelForm):
    ticket_price_minor = forms.DecimalField(
        label="Section ticket price (M)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        help_text="Set 0.00 for a free section. Leave blank to use the event ticket category price.",
    )
    price_modifier_minor = forms.DecimalField(
        label="Additional section supplement (M)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        help_text="Optional additional charge applied on top of the section or category price.",
    )

    class Meta:
        model = SeatingSection
        fields = (
            "name",
            "description",
            "color",
            "ticket_price_minor",
            "price_modifier_minor",
            "is_accessible",
            "sort_order",
        )
