from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation
from seating.models import EventSeating, Seat, SeatReservation, SeatingRow, SeatingSection
from ticketing.models import Event, Ticket, TicketCategory
from venues.models import Venue

from .fulfillment import fulfill_paid_order
from .models import Order, OrderLine


class CheckoutCorrectnessTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(email="buyer@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Checkout Org", slug="checkout-org")
        self.event = Event.objects.create(
            organisation=organisation,
            name="Checkout Event",
            starts_at=timezone.now() + timedelta(days=2),
            status=Event.Status.SALES_OPEN,
        )
        self.category = TicketCategory.objects.create(
            event=self.event, name="Standard", price_minor=2500, total_quantity=10
        )
        self.client.force_login(self.customer)

    def test_repeated_order_submission_returns_existing_order(self):
        payload = {
            "ticket_category": str(self.category.pk),
            "quantity": "1",
            "idempotency_key": "checkout-attempt-1",
        }
        first = self.client.post(reverse("orders:order-create", args=[self.event.pk]), payload)
        second = self.client.post(reverse("orders:order-create", args=[self.event.pk]), payload)

        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)
        self.assertRedirects(second, first["Location"])

    def test_category_sales_window_is_enforced(self):
        self.category.sales_opens_at = timezone.now() + timedelta(hours=1)
        self.category.save(update_fields=["sales_opens_at"])

        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {"ticket_category": str(self.category.pk), "quantity": "1", "idempotency_key": "future"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not on sale yet")
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())


class SeatFulfillmentTests(TestCase):
    def test_expired_reservation_cannot_be_fulfilled(self):
        owner = User.objects.create_user(email="seat-buyer@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Seat Org", slug="seat-org")
        venue = Venue.objects.create(organisation=organisation, name="Hall", slug="hall")
        event = Event.objects.create(
            organisation=organisation,
            name="Seat Event",
            venue=venue,
            starts_at=timezone.now() + timedelta(days=2),
            status=Event.Status.SALES_OPEN,
        )
        category = TicketCategory.objects.create(event=event, name="Seat", price_minor=3000, total_quantity=1)
        EventSeating.objects.create(event=event, venue=venue)
        section = SeatingSection.objects.create(venue=venue, name="Main")
        row = SeatingRow.objects.create(section=section, name="A")
        seat = Seat.objects.create(row=row, number="1", label="A-1")
        reservation = SeatReservation.objects.create(
            event=event,
            seat=seat,
            session_key="expired-session",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        order = Order.objects.create(customer=owner, event=event, status=Order.Status.PAID, total_minor=3000)
        OrderLine.objects.create(
            order=order,
            line_type=OrderLine.LineType.SEAT,
            ticket_category=category,
            seat=seat,
            seat_reservation=reservation,
            unit_price_minor=3000,
            quantity=1,
            line_total_minor=3000,
        )

        with self.assertRaisesMessage(ValueError, "seat hold has expired"):
            fulfill_paid_order(order_id=order.pk)
        self.assertFalse(Ticket.objects.filter(order=order).exists())
