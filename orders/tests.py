from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation
from seating.models import EventSeating, Seat, SeatReservation, SeatingRow, SeatingSection
from ticketing.models import Event, Ticket, TicketCategory
from venues.models import Venue

from .fulfillment import fulfill_paid_order
from .models import InventoryHold, Order, OrderLine
from .services import expire_order_if_holds_expired
from finance.models import PlatformCommissionConfig
from payments.models import Payment


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
            event=self.event, name="Standard", price_minor="25.00", total_quantity=10
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

    def test_checkout_shows_price_summary_and_safe_retry_message(self):
        response = self.client.get(reverse("orders:order-create", args=[self.event.pk]))

        self.assertContains(response, "Estimated total")
        self.assertContains(response, "25.00")
        self.assertContains(response, "safety key")

    def test_purchase_history_shows_payment_ticket_and_event_links(self):
        order = Order.objects.create(customer=self.customer, event=self.event, total_minor="25.00")
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.MPESA,
            status=Payment.Status.PENDING,
            amount_minor="25.00",
        )

        response = self.client.get(reverse("orders:order-list"))

        self.assertContains(response, "Pending")
        self.assertContains(response, "View order")
        self.assertContains(response, "View event")

    def test_new_checkout_has_no_customer_fee_and_snapshots_commission(self):
        config = PlatformCommissionConfig.current()
        config.commission_rate = "10.00"
        config.save(update_fields=["commission_rate", "updated_at"])
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {"ticket_category": str(self.category.pk), "quantity": "1", "idempotency_key": "commission-checkout"},
        )
        order = Order.objects.get(customer=self.customer)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.subtotal_minor, Decimal("25.00"))
        self.assertEqual(order.total_minor, Decimal("25.00"))
        self.assertEqual(order.fee_minor, Decimal("0.00"))
        self.assertEqual(order.commission_minor, Decimal("2.50"))
        detail = self.client.get(response["Location"])
        self.assertNotContains(detail, "Service fee")
        self.assertContains(detail, "M 25.00")

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

    def test_pending_order_expires_after_its_inventory_hold_ends(self):
        order = Order.objects.create(customer=self.customer, event=self.event, total_minor="25.00")
        InventoryHold.objects.create(
            order=order,
            ticket_category=self.category,
            quantity=1,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        self.assertTrue(expire_order_if_holds_expired(order))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        self.assertEqual(order.inventory_holds.get().status, InventoryHold.Status.EXPIRED)

    def test_order_detail_shows_active_reservation_expiry(self):
        order = Order.objects.create(customer=self.customer, event=self.event, total_minor="25.00")
        InventoryHold.objects.create(
            order=order,
            ticket_category=self.category,
            quantity=1,
            expires_at=timezone.now() + timedelta(minutes=8),
        )

        response = self.client.get(reverse("orders:order-detail", args=[order.pk]))

        self.assertContains(response, "Your ticket reservation expires in")
        self.assertContains(response, "data-reservation-countdown")


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
        category = TicketCategory.objects.create(event=event, name="Seat", price_minor="30.00", total_quantity=1)
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
        order = Order.objects.create(customer=owner, event=event, status=Order.Status.PAID, total_minor="30.00")
        OrderLine.objects.create(
            order=order,
            line_type=OrderLine.LineType.SEAT,
            ticket_category=category,
            seat=seat,
            seat_reservation=reservation,
            unit_price_minor="30.00",
            quantity=1,
            line_total_minor="30.00",
        )

        with self.assertRaisesMessage(ValueError, "seat hold has expired"):
            fulfill_paid_order(order_id=order.pk)
        self.assertFalse(Ticket.objects.filter(order=order).exists())
