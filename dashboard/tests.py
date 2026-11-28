import base64
from decimal import Decimal

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation, OrganisationMembership
from organisations.models import OrganisationPaymentMethod
from orders.models import Order
from payments.models import Payment, PaymentReview
from ticketing.models import Event


class PendingPaymentsDashboardTests(TestCase):
    def setUp(self):
        self.organiser = User.objects.create_user(
            email="organiser@example.com", password="pass-12345"
        )
        self.customer = User.objects.create_user(
            email="customer@example.com", password="pass-12345"
        )
        organisation = Organisation.objects.create(
            name="Pending Events", slug="pending-events"
        )
        OrganisationMembership.objects.create(
            organisation=organisation,
            user=self.organiser,
            role=OrganisationMembership.Role.OWNER,
        )
        self.event = Event.objects.create(
            organisation=organisation,
            name="Pending Night",
            starts_at=timezone.now(),
        )
        self.payment_method = OrganisationPaymentMethod.objects.create(
            organisation=organisation,
            provider=OrganisationPaymentMethod.Provider.MPESA,
            label="Events M-Pesa",
            account_number="58590000",
        )
        self.second_payment_method = OrganisationPaymentMethod.objects.create(
            organisation=organisation,
            provider=OrganisationPaymentMethod.Provider.ECOCASH,
            label="Events EcoCash",
            account_number="63010000",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            event=self.event,
            total_minor="25.00",
        )

    def test_organiser_can_view_pending_orders_for_their_events(self):
        self.client.force_login(self.organiser)
        response = self.client.get(reverse("pending-payments"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.reference)
        self.assertContains(response, "Awaiting customer proof")

    def test_customer_is_not_given_organiser_payment_view(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("pending-payments"))
        self.assertRedirects(response, reverse("customer-dashboard"))

    def test_customer_submits_proof_and_organiser_approves_it(self):
        self.client.force_login(self.customer)
        detail = self.client.get(reverse("orders:order-detail", args=[self.order.pk]))
        self.assertContains(detail, "58590000")
        self.assertContains(detail, "63010000")
        response = self.client.post(
            reverse("orders:order-detail", args=[self.order.pk]),
            {
                "payment_method": str(self.payment_method.pk),
                "provider_reference": "MPESA-12345",
                "sender_phone": "+26650123456",
                "proof_image": SimpleUploadedFile(
                    "proof.png",
                    base64.b64decode(
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                    ),
                    content_type="image/png",
                ),
            },
        )
        self.assertRedirects(response, reverse("orders:order-detail", args=[self.order.pk]))
        payment = self.order.payments.get()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.provider_reference, "MPESA-12345")
        self.assertEqual(payment.payment_method_id, self.payment_method.pk)

        self.client.force_login(self.organiser)
        response = self.client.post(
            reverse("review-payment", args=[payment.pk]),
            {"decision": "approve", "received_amount_maloti": "25.00", "review_note": "Payment matched."},
        )
        self.assertRedirects(response, reverse("pending-payments"))
        payment = payment.__class__.objects.get(pk=payment.pk)
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, Order.Status.PAID)
        self.assertEqual(payment.sender_phone, "+26650123456")
        self.assertEqual(payment.received_amount_minor, Decimal("25.00"))
        self.assertEqual(payment.review_history.count(), 1)

    def test_customer_can_check_payment_status(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("orders:payment-status", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order_reference"], self.order.reference)
        self.assertEqual(response.json()["payment_status"], "not_submitted")

    def test_customer_can_submit_manual_ecocash_payment(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("orders:order-detail", args=[self.order.pk]),
            {
                "payment_method": str(self.second_payment_method.pk),
                "provider_reference": "ecocash-123",
                "sender_phone": "+26650123456",
            },
        )
        self.assertEqual(response.status_code, 302)
        payment = self.order.payments.get()
        self.assertEqual(payment.provider, Payment.Provider.ECOCASH)
        self.assertEqual(payment.provider_reference, "ECOCASH-123")

    def test_expired_order_cannot_receive_a_manual_payment_submission(self):
        self.order.status = Order.Status.EXPIRED
        self.order.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("orders:order-detail", args=[self.order.pk]),
            {
                "payment_method": str(self.payment_method.pk),
                "provider_reference": "EXPIRED-1",
                "sender_phone": "+26650123456",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.filter(order=self.order).exists())

    def test_duplicate_transaction_reference_is_rejected(self):
        from payments.forms import ManualPaymentForm

        Payment.objects.create(
            order=self.order,
            payment_method=self.payment_method,
            provider=Payment.Provider.MPESA,
            provider_reference="DUPLICATE-1",
            amount_minor=self.order.total_minor,
        )
        form = ManualPaymentForm(
            data={
                "payment_method": str(self.payment_method.pk),
                "provider_reference": "duplicate-1",
                "sender_phone": "+26650123456",
            },
            organisation=self.event.organisation,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("already been submitted", str(form.errors))

    def test_incorrect_verified_amount_does_not_approve_payment(self):
        self.client.force_login(self.customer)
        self.client.post(
            reverse("orders:order-detail", args=[self.order.pk]),
            {
                "payment_method": str(self.payment_method.pk),
                "provider_reference": "MPESA-WRONG-AMOUNT",
                "sender_phone": "+26650123456",
            },
        )
        payment = self.order.payments.get()
        self.client.force_login(self.organiser)
        self.client.post(
            reverse("review-payment", args=[payment.pk]),
            {"decision": "approve", "received_amount_maloti": "20.00"},
        )
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, Payment.Status.PENDING)
        self.assertEqual(PaymentReview.objects.filter(payment=payment).count(), 0)

    def test_event_staff_cannot_review_payments(self):
        staff = User.objects.create_user(email="event-staff@example.com", password="pass-12345")
        OrganisationMembership.objects.create(
            organisation=self.order.event.organisation,
            user=staff,
            role="event_staff",
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("pending-payments"))
        self.assertEqual(response.status_code, 403)

    def test_rejected_payment_creates_review_history(self):
        payment = Payment.objects.create(
            order=self.order,
            payment_method=self.payment_method,
            provider=Payment.Provider.MPESA,
            provider_reference="MPESA-REJECT-1",
            amount_minor=self.order.total_minor,
            sender_phone="+26650123456",
        )
        self.client.force_login(self.organiser)
        response = self.client.post(
            reverse("review-payment", args=[payment.pk]),
            {"decision": "reject", "review_note": "Reference not found in provider records."},
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        review = payment.review_history.get()
        self.assertEqual(review.decision, PaymentReview.Decision.REJECTED)

    def test_rejection_requires_an_auditable_reason(self):
        from payments.forms import PaymentReviewForm

        form = PaymentReviewForm(data={"decision": "reject", "review_note": "  "})

        self.assertFalse(form.is_valid())
        self.assertIn("Explain why this payment was rejected.", str(form.errors))

    def test_sender_phone_is_normalised_before_storage(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("orders:order-detail", args=[self.order.pk]),
            {
                "payment_method": str(self.payment_method.pk),
                "provider_reference": "MPESA-NORMALISED-1",
                "sender_phone": "050 123 4567",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.order.payments.get().sender_phone, "+266501234567")

    def test_payment_confirmation_requires_transaction_reference(self):
        from payments.services import confirm_payment

        payment = Payment.objects.create(
            order=self.order,
            payment_method=self.payment_method,
            provider=Payment.Provider.MPESA,
            amount_minor=self.order.total_minor,
        )

        with self.assertRaisesMessage(ValueError, "provider transaction reference is required"):
            confirm_payment(payment_id=payment.pk, provider_reference="")

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_organiser_cannot_start_customer_checkout(self):
        self.client.force_login(self.organiser)
        response = self.client.get(reverse("orders:order-create", args=[self.event.pk]))
        self.assertRedirects(response, reverse("dashboard"))

    def test_public_event_detail_renders_category_price(self):
        category = self.event.ticket_categories.create(
            name="General admission",
            price_minor="12.50",
            total_quantity=20,
        )
        self.event.status = Event.Status.PUBLISHED
        self.event.save(update_fields=["status"])

        response = self.client.get(reverse("public-event-detail", args=[self.event.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "M 12.50")

    def test_public_event_filters_by_category_location_and_date(self):
        from datetime import timedelta

        from venues.models import Venue

        category = self.event.ticket_categories.create(
            name="Jazz", price_minor="15.00", total_quantity=20
        )
        venue = Venue.objects.create(
            organisation=self.event.organisation, name="Maseru Hall", slug="maseru-hall", city="Maseru"
        )
        self.event.venue = venue
        self.event.status = Event.Status.PUBLISHED
        self.event.starts_at = timezone.now() + timedelta(days=5)
        self.event.save(update_fields=["venue", "status", "starts_at"])

        response = self.client.get(
            reverse("public-event-list"),
            {"category": "Jazz", "location": "Maseru", "date_from": (timezone.now() + timedelta(days=4)).date().isoformat()},
        )

        self.assertContains(response, self.event.name)
        self.assertContains(response, category.name)

    def test_public_event_filters_by_ticket_format_and_reports_invalid_dates(self):
        from datetime import timedelta

        self.event.ticket_categories.create(name="General", price_minor="10.00", total_quantity=5)
        self.event.status = Event.Status.PUBLISHED
        self.event.save(update_fields=["status"])
        reserved = Event.objects.create(
            organisation=self.event.organisation,
            name="Reserved Night",
            starts_at=timezone.now() + timedelta(days=2),
            status=Event.Status.PUBLISHED,
            ticketing_model=Event.TicketingModel.RESERVED_SEATING,
        )
        reserved.ticket_categories.create(name="Seat", price_minor="20.00", total_quantity=5)

        response = self.client.get(
            reverse("public-event-list"),
            {"ticketing_model": "reserved_seating", "date_from": "not-a-date"},
        )

        self.assertContains(response, reserved.name)
        self.assertNotContains(response, self.event.name)
        self.assertContains(response, "Use valid dates to filter events.")

    def test_customer_order_page_explains_live_payment_status(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("orders:order-detail", args=[self.order.pk]))
        self.assertContains(response, "Payment status")
        self.assertContains(response, "Not submitted")
        self.assertContains(response, "Refresh status")

    def test_organiser_can_download_event_attendee_and_admission_report(self):
        from ticketing.models import Admission, Ticket

        ticket = Ticket.objects.create(
            event=self.event,
            owner=self.customer,
            reference="REPORT-1",
            attendee_name="Report Attendee",
            payment_verified_at=timezone.now(),
        )
        Admission.objects.create(
            ticket=ticket,
            event=self.event,
            admitted_by=self.organiser,
            gate="North gate",
        )
        self.client.force_login(self.organiser)

        response = self.client.get(reverse("event-attendee-export", args=[self.event.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("REPORT-1", body)
        self.assertIn("Report Attendee", body)
        self.assertIn("North gate", body)

    def test_event_operations_page_links_to_attendees_refunds_and_settlements(self):
        self.client.force_login(self.organiser)

        response = self.client.get(reverse("ticketing:event-detail", args=[self.event.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("event-attendee-export", args=[self.event.pk]))
        self.assertContains(response, reverse("event-organiser-refunds", args=[self.event.pk]))
        self.assertContains(
            response,
            reverse("finance:event-report", args=[self.event.pk]),
        )

    def test_authorised_event_staff_can_filter_the_attendee_roster(self):
        from ticketing.models import Ticket

        ticket = Ticket.objects.create(
            event=self.event,
            owner=self.customer,
            reference="ATTENDEE-1",
            attendee_name="Roster Customer",
            payment_verified_at=timezone.now(),
        )
        self.client.force_login(self.organiser)

        response = self.client.get(
            reverse("ticketing:attendee-list", args=[self.event.pk]),
            {"q": "Roster", "status": ticket.status},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Roster Customer")
        self.assertContains(response, "ATTENDEE-1")

    def test_event_staff_cannot_change_event_lifecycle_or_categories(self):
        staff = User.objects.create_user(email="operations-staff@example.com", password="pass-12345")
        OrganisationMembership.objects.create(
            organisation=self.event.organisation,
            user=staff,
            role=OrganisationMembership.Role.EVENT_STAFF,
        )
        self.client.force_login(staff)

        publish = self.client.post(reverse("ticketing:event-publish", args=[self.event.pk]))
        category_create = self.client.get(
            reverse("ticketing:ticket-category-create", args=[self.event.pk])
        )

        self.assertEqual(publish.status_code, 403)
        self.assertEqual(category_create.status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.Status.DRAFT)

    def test_event_payment_queue_is_scoped_to_the_selected_event(self):
        other_event = Event.objects.create(
            organisation=self.event.organisation, name="Other Queue Event", starts_at=timezone.now()
        )
        other_order = Order.objects.create(customer=self.customer, event=other_event, total_minor="30.00")
        self.client.force_login(self.organiser)

        response = self.client.get(reverse("event-pending-payments", args=[self.event.pk]))

        self.assertContains(response, self.order.reference)
        self.assertNotContains(response, other_order.reference)

    def test_organiser_report_cannot_cross_organisation_boundaries(self):
        other = User.objects.create_user(email="other-organiser@example.com", password="pass-12345")
        other_organisation = Organisation.objects.create(name="Other Events", slug="other-events")
        OrganisationMembership.objects.create(
            organisation=other_organisation,
            user=other,
            role=OrganisationMembership.Role.OWNER,
        )
        self.client.force_login(other)
        response = self.client.get(reverse("event-attendee-export", args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)


class PlatformDashboardTests(TestCase):
    def test_only_superusers_can_view_platform_dashboard(self):
        user = User.objects.create_user(email="platform@example.com", password="pass-12345")
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])

        self.client.force_login(user)
        response = self.client.get(reverse("platform-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform owner dashboard")
        self.assertContains(response, "Private signing and encryption values remain")

    def test_regular_staff_user_cannot_view_platform_dashboard(self):
        user = User.objects.create_user(email="staff@example.com", password="pass-12345")
        user.is_staff = True
        user.save(update_fields=["is_staff"])

        self.client.force_login(user)
        response = self.client.get(reverse("platform-dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_platform_owner_can_suspend_and_reactivate_user(self):
        owner = User.objects.create_superuser(email="owner@example.com", password="pass-12345")
        target = User.objects.create_user(email="target@example.com", password="pass-12345")
        self.client.force_login(owner)

        response = self.client.post(reverse("platform-user-toggle", args=[target.pk]))
        self.assertRedirects(response, reverse("platform-dashboard"))
        self.assertFalse(User.objects.get(pk=target.pk).is_active)

        self.client.post(reverse("platform-user-toggle", args=[target.pk]))
        self.assertTrue(User.objects.get(pk=target.pk).is_active)

    def test_platform_owner_can_pause_event(self):
        owner = User.objects.create_superuser(email="event-owner@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Platform Events", slug="platform-events")
        event = Event.objects.create(
            organisation=organisation,
            name="Platform Test Event",
            starts_at=timezone.now(),
            status=Event.Status.SALES_OPEN,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("platform-event-action", args=[event.pk]),
            {"action": "suspend"},
        )
        self.assertRedirects(response, reverse("platform-dashboard"))
        self.assertEqual(Event.objects.get(pk=event.pk).status, Event.Status.SALES_PAUSED)
