from django import forms

from seating.models import Seat
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
                self.fields["seat"] = forms.ChoiceField(
                    label="Seat",
                    choices=[(str(s.id), s.label) for s in Seat.objects.filter(row__section__venue=event.venue, status=Seat.Status.AVAILABLE).select_related("row__section")],
                    required=False,
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
        seat = cleaned_data.get("seat")
        quantity = cleaned_data.get("quantity")

        # Validation: ticket category or seat must be selected
        if not ticket_category:
            self.add_error("ticket_category", "Choose a ticket category.")

        if self.event and self.event.ticketing_model == Event.TicketingModel.RESERVED_SEATING and not seat:
            self.add_error("seat", "Choose a seat.")

        # Validation: quantity must be provided for GA
        if self.event and not quantity and self.event.ticketing_model == Event.TicketingModel.GENERAL_ADMISSION:
            self.add_error("quantity", "Quantity is required for general admission tickets.")

        return cleaned_data
