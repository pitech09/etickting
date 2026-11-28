from django import forms

from ticketing.models import Event, TicketCategory


class OrderCreateForm(forms.Form):
    """Form for creating an order during checkout."""

    def __init__(self, *args, event=None, user=None, **kwargs):
        self.event = event
        self.user = user
        super().__init__(*args, **kwargs)
        if event:
            # Add ticket category choices
            self.fields["ticket_category"] = forms.ChoiceField(
                label="Ticket category",
                choices=[(str(tc.id), tc.name) for tc in TicketCategory.objects.filter(event=event, is_active=True).select_related("event")],
                required=True,
            )
            # Add seat choices if reserved seating
            if event.ticketing_model == Event.TicketingModel.RESERVED_SEATING:
                self.fields["quantity"] = forms.IntegerField(
                    label="Number of seats",
                    min_value=1,
                    initial=1,
                    required=True,
                    widget=forms.NumberInput(attrs={"min": 1}),
                )
                self.fields["seat_ids"] = forms.CharField(
                    required=False,
                    widget=forms.HiddenInput(),
                )
            # Add quantity field for general admission
            if event.ticketing_model == Event.TicketingModel.GENERAL_ADMISSION:
                self.fields["quantity"] = forms.IntegerField(
                    label="Quantity",
                    min_value=1,
                    initial=1,
                    required=False,
                )

    def clean(self):
        cleaned_data = super().clean()
        ticket_category = cleaned_data.get("ticket_category")
        seat_ids = [value.strip() for value in (cleaned_data.get("seat_ids") or "").split(",") if value.strip()]
        quantity = cleaned_data.get("quantity")

        # Validation: ticket category or seat must be selected
        if not ticket_category:
            self.add_error("ticket_category", "Choose a ticket category.")

        if self.event and self.event.ticketing_model == Event.TicketingModel.RESERVED_SEATING:
            if not seat_ids:
                self.add_error("seat_ids", "Choose your seats on the seating map.")
            elif quantity and len(seat_ids) != quantity:
                self.add_error("seat_ids", f"Choose exactly {quantity} seat(s).")
            cleaned_data["seat_ids"] = seat_ids

        # Validation: quantity must be provided for GA
        if self.event and not quantity and self.event.ticketing_model == Event.TicketingModel.GENERAL_ADMISSION:
            self.add_error("quantity", "Quantity is required for general admission tickets.")

        return cleaned_data
