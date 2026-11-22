import base64

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation, OrganisationMembership
from organisations.models import OrganisationPaymentMethod
from orders.models import Order
from payments.models import Payment
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
            total_minor=2500,
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
            {"decision": "approve", "review_note": "Payment matched."},
        )
        self.assertRedirects(response, reverse("pending-payments"))
        self.assertEqual(payment.__class__.objects.get(pk=payment.pk).status, Payment.Status.SUCCESSFUL)
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, Order.Status.PAID)

    def test_organiser_cannot_start_customer_checkout(self):
        self.client.force_login(self.organiser)
        response = self.client.get(reverse("orders:order-create", args=[self.event.pk]))
        self.assertRedirects(response, reverse("dashboard"))

    def test_public_event_detail_renders_category_price(self):
        category = self.event.ticket_categories.create(
            name="General admission",
            price_minor=1250,
            total_quantity=20,
        )
        self.event.status = Event.Status.PUBLISHED
        self.event.save(update_fields=["status"])

        response = self.client.get(reverse("public-event-detail", args=[self.event.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "M 12.50")
