import base64
import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation
from seating.models import EventSectionPricing, EventSeating, Seat, SeatReservation, SeatingRow, SeatingSection
from ticketing.models import Event, Ticket, TicketCategory
from venues.models import Venue

from .fulfillment import fulfill_paid_order
from .models import InventoryHold, Order, OrderLine
from .services import expire_order_if_holds_expired
from finance.models import PlatformCommissionConfig
from payments.models import Payment
from seating.services import reserve_seats


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
    def setUp(self):
        self.owner = User.objects.create_user(email="reserved-buyer@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Reserved Org", slug="reserved-org")
        venue = Venue.objects.create(organisation=organisation, name="Reserved Hall", slug="reserved-hall")
        self.event = Event.objects.create(
            organisation=organisation,
            name="Reserved Event",
            venue=venue,
            ticketing_model=Event.TicketingModel.RESERVED_SEATING,
            starts_at=timezone.now() + timedelta(days=2),
            status=Event.Status.SALES_OPEN,
        )
        self.category = TicketCategory.objects.create(
            event=self.event, name="Standard", price_minor="30.00", total_quantity=2, max_per_customer=2
        )
        EventSeating.objects.create(event=self.event, venue=venue)
        section = SeatingSection.objects.create(venue=venue, name="Main")
        self.section = section
        row = SeatingRow.objects.create(section=section, name="A")
        self.seats = [
            Seat.objects.create(row=row, number=str(index), label=f"A-{index}")
            for index in (1, 2)
        ]

    def test_reserved_checkout_accepts_exactly_selected_seat_quantity(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {
                "ticket_category": str(self.category.pk),
                "quantity": "2",
                "seat_ids": ",".join(str(seat.pk) for seat in self.seats),
                "price": "0.00",
                "idempotency_key": "reserved-two-seats",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(reference__isnull=False, customer=self.owner)
        self.assertEqual(order.lines.filter(line_type=OrderLine.LineType.SEAT).count(), 2)
        self.assertEqual(order.subtotal_minor, Decimal("60.00"))
        self.assertEqual(SeatReservation.objects.filter(event=self.event, status=SeatReservation.Status.ACTIVE).count(), 2)

        self.section.ticket_price_minor = "99.00"
        self.section.save(update_fields=["ticket_price_minor"])
        self.assertEqual(list(order.lines.values_list("unit_price_minor", flat=True)), [Decimal("30.00"), Decimal("30.00")])

    def test_reserved_seat_hold_defaults_to_24_hours(self):
        before = timezone.now()
        reservations, errors = reserve_seats(
            event=self.event,
            seat_ids=[self.seats[0].pk],
            session_key="24-hour-seat-hold",
        )

        self.assertFalse(errors)
        self.assertEqual(len(reservations), 1)
        duration = reservations[0].expires_at - before
        self.assertGreaterEqual(duration.total_seconds(), (24 * 60 - 1) * 60)
        self.assertLessEqual(duration.total_seconds(), (24 * 60 + 1) * 60)

    def test_reserved_checkout_applies_section_supplement_per_seat(self):
        self.section.price_modifier_minor = "5.50"
        self.section.save(update_fields=["price_modifier_minor"])
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {
                "ticket_category": str(self.category.pk),
                "quantity": "2",
                "seat_ids": ",".join(str(seat.pk) for seat in self.seats),
                "idempotency_key": "reserved-supplement",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(reference__isnull=False, customer=self.owner)
        self.assertEqual(list(order.lines.values_list("unit_price_minor", flat=True)), [Decimal("35.50"), Decimal("35.50")])
        self.assertEqual(order.total_minor, Decimal("71.00"))

    def test_reserved_checkout_uses_section_ticket_price_over_category_price(self):
        self.section.ticket_price_minor = "45.00"
        self.section.price_modifier_minor = "5.00"
        self.section.save(update_fields=["ticket_price_minor", "price_modifier_minor"])
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {
                "ticket_category": str(self.category.pk),
                "quantity": "1",
                "seat_ids": str(self.seats[0].pk),
                "idempotency_key": "section-base-price",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(reference__isnull=False, customer=self.owner)
        self.assertEqual(order.lines.get().unit_price_minor, Decimal("50.00"))
        self.assertEqual(order.total_minor, Decimal("50.00"))

    def test_reserved_checkout_uses_event_section_category_price_and_ignores_tampering(self):
        EventSectionPricing.objects.create(
            event=self.event,
            section=self.section,
            ticket_category=self.category,
            price_minor="75.00",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {
                "ticket_category": str(self.category.pk),
                "quantity": "2",
                "seat_ids": ",".join(str(seat.pk) for seat in self.seats),
                "price": "0.01",
                "idempotency_key": "event-section-price",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(customer=self.owner)
        self.assertEqual(list(order.lines.values_list("unit_price_minor", flat=True)), [Decimal("75.00"), Decimal("75.00")])
        self.assertEqual(order.total_minor, Decimal("150.00"))

    def test_reserved_checkout_allows_a_genuinely_free_ticket(self):
        self.category.price_minor = "0.00"
        self.category.save(update_fields=["price_minor"])
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {
                "ticket_category": str(self.category.pk),
                "quantity": "1",
                "seat_ids": str(self.seats[0].pk),
                "idempotency_key": "reserved-free-seat",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(reference__isnull=False, customer=self.owner)
        self.assertEqual(order.total_minor, Decimal("0.00"))

    def test_reserved_checkout_rejects_quantity_mismatch(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("orders:order-create", args=[self.event.pk]),
            {
                "ticket_category": str(self.category.pk),
                "quantity": "2",
                "seat_ids": str(self.seats[0].pk),
                "idempotency_key": "reserved-one-of-two",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose exactly 2 seat(s)")
        self.assertFalse(Order.objects.filter(customer=self.owner).exists())

    @override_settings(TICKETING_SIGNING_KEYS=json.dumps({"test-key": base64.urlsafe_b64encode(b"1" * 32).decode()}))
    def test_paid_reserved_order_issues_one_ticket_per_selected_seat(self):
        order = Order.objects.create(
            customer=self.owner, event=self.event, status=Order.Status.PAID, total_minor="60.00"
        )
        reservations = [
            SeatReservation.objects.create(
                event=self.event,
                seat=seat,
                session_key="paid-session",
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            for seat in self.seats
        ]
        for seat, reservation in zip(self.seats, reservations):
            OrderLine.objects.create(
                order=order,
                line_type=OrderLine.LineType.SEAT,
                ticket_category=self.category,
                seat=seat,
                seat_reservation=reservation,
                unit_price_minor="30.00",
                quantity=1,
                line_total_minor="30.00",
            )

        tickets = fulfill_paid_order(order_id=order.pk)

        self.assertEqual(len(tickets), 2)
        self.assertEqual(set(Ticket.objects.filter(order=order).values_list("seat_label", flat=True)), {"A-1", "A-2"})
        self.assertEqual(SeatReservation.objects.filter(event=self.event, status=SeatReservation.Status.CONVERTED).count(), 2)

    def test_reserved_seat_map_exposes_quantity_controls_and_seats(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("seating:event-seat-map", args=[self.event.pk]))

        self.assertRedirects(response, reverse("orders:order-create", args=[self.event.pk]))
        checkout = self.client.get(reverse("orders:order-create", args=[self.event.pk]))
        self.assertEqual(checkout.status_code, 200)
        self.assertContains(checkout, 'id="seat-map"')
        self.assertContains(checkout, "A-1")
        self.assertContains(checkout, "A-2")
        self.assertContains(checkout, "30.00")
        self.assertContains(checkout, "Select as many seats")

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
