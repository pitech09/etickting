import base64
from io import BytesIO
import json
from datetime import timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from organisations.models import Organisation, OrganisationMembership
from seating.models import EventSeating, Seat

from .inventory import inventory_snapshot
from .models import Admission, Event, ResaleListing, ScanAttempt, ScannerDevice, Ticket, TicketCategory, TicketCredential
from .services import admit_ticket, create_resale_listing, issue_ticket, purchase_resale, transfer_ticket, verify_credential
from .key_management import signing_keys


def encoded_key(key):
    return base64.urlsafe_b64encode(key.private_bytes_raw()).decode()


def encoded_public(key):
    return base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode()


class TicketAuthenticityTests(TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.signing = json.dumps({"key-1": encoded_key(self.private)})
        self.settings = override_settings(TICKETING_SIGNING_KEYS=self.signing, TICKETING_VERIFY_KEYS="")
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.owner = User.objects.create_user(email="holder@example.com", password="pass-12345")
        self.other = User.objects.create_user(email="new-holder@example.com", password="pass-12345")
        self.organisation = Organisation.objects.create(name="Authentic Events", slug="authentic-events")
        self.staff = User.objects.create_user(email="staff@example.com", password="pass-12345")
        OrganisationMembership.objects.create(organisation=self.organisation, user=self.staff, role=OrganisationMembership.Role.EVENT_STAFF)
        self.event = Event.objects.create(organisation=self.organisation, name="Verified Night", starts_at=timezone.now(), status=Event.Status.PUBLISHED)
        self.device = ScannerDevice.objects.create(device_id="scanner-1", event=self.event, user=self.staff)

    def issue(self):
        return issue_ticket(event=self.event, owner=self.owner, payment_verified=True, attendee_name="Private Attendee", seat_label="A-1")

    def test_unpaid_ticket_cannot_be_issued(self):
        with self.assertRaisesMessage(Exception, "requires verified payment"):
            issue_ticket(event=self.event, owner=self.owner)

    def test_development_has_deterministic_signing_key_without_deployment_secret(self):
        with override_settings(DEBUG=True, TICKETING_SIGNING_KEYS=""):
            self.assertIn("development", signing_keys())

        with override_settings(DEBUG=False, TICKETING_SIGNING_KEYS=""):
            self.assertEqual(signing_keys(), {})

    def test_forged_and_modified_credentials_fail(self):
        _, credential = self.issue()
        self.assertEqual(verify_credential(credential)[1], "valid")
        parts = credential.split(".")
        parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
        self.assertEqual(verify_credential(".".join(parts))[1], "invalid")
        self.assertEqual(verify_credential("unknown." + ".".join(credential.split(".")[1:]))[1], "invalid")

    def test_cancelled_refunded_and_transferred_credentials_are_rejected(self):
        ticket, credential = self.issue()
        ticket.status = Ticket.Status.CANCELLED
        ticket.save(update_fields=["status"])
        self.assertEqual(verify_credential(credential)[1], "cancelled")
        ticket.status = Ticket.Status.ISSUED
        ticket.save(update_fields=["status"])
        ticket.status = Ticket.Status.REFUNDED
        ticket.save(update_fields=["status"])
        self.assertEqual(verify_credential(credential)[1], "refunded")
        ticket.status = Ticket.Status.ISSUED
        ticket.save(update_fields=["status"])
        old_credential = credential
        ticket, new_credential = transfer_ticket(ticket_id=ticket.id, current_owner=self.owner, new_owner=self.other)
        self.assertEqual(verify_credential(old_credential)[1], "transferred")
        self.assertEqual(verify_credential(new_credential)[1], "valid")
        self.assertEqual(ticket.owner_id, self.other.id)
        self.assertEqual(TicketCredential.objects.filter(ticket=ticket).count(), 2)

    def test_resale_requires_payment_and_locks_listing(self):
        ticket, old_credential = self.issue()
        listing = create_resale_listing(ticket_id=ticket.id, seller=self.owner, price_minor=1000)
        with self.assertRaisesMessage(Exception, "payment must be verified"):
            purchase_resale(listing_id=listing.id, buyer=self.other, payment_verified=False)
        ticket, new_credential = purchase_resale(listing_id=listing.id, buyer=self.other, payment_verified=True)
        self.assertEqual(ResaleListing.objects.get(pk=listing.pk).status, ResaleListing.Status.SOLD)
        self.assertEqual(verify_credential(old_credential)[1], "transferred")
        self.assertEqual(verify_credential(new_credential)[1], "valid")
        with self.assertRaises(Exception):
            purchase_resale(listing_id=listing.id, buyer=self.owner, payment_verified=True)

    def test_key_rotation_keeps_old_credentials_verifiable(self):
        _, credential = self.issue()
        next_private = Ed25519PrivateKey.generate()
        with override_settings(TICKETING_SIGNING_KEYS=json.dumps({"key-2": encoded_key(next_private)}), TICKETING_VERIFY_KEYS=json.dumps({"key-1": encoded_public(self.private)})):
            self.assertEqual(verify_credential(credential)[1], "valid")

    def test_atomic_scan_allows_one_admission_and_rejects_replay(self):
        _, credential = self.issue()
        first, first_result = admit_ticket(credential=credential, event=self.event, user=self.staff, device_id=self.device.device_id)
        second, second_result = admit_ticket(credential=credential, event=self.event, user=self.staff, device_id=self.device.device_id)
        self.assertEqual(first_result, "valid")
        self.assertEqual(second_result, "used")
        self.assertEqual(Admission.objects.count(), 1)
        self.assertEqual(ScanAttempt.objects.filter(result=ScanAttempt.Result.USED).count(), 1)
        self.assertEqual(first.owner_id, self.owner.id)

    def test_reentry_policy_records_reentry_without_issuing_a_second_admission(self):
        self.event.admission_policy = "reentry"
        self.event.save(update_fields=["admission_policy"])
        _, credential = self.issue()
        self.assertEqual(admit_ticket(credential=credential, event=self.event, user=self.staff, device_id=self.device.device_id)[1], "valid")
        self.assertEqual(admit_ticket(credential=credential, event=self.event, user=self.staff, device_id=self.device.device_id)[1], "reentry")
        self.assertEqual(Admission.objects.get().reentry_count, 1)

    def test_offline_batch_accepts_signature_for_reconciliation(self):
        _, credential = self.issue()
        self.client.force_login(self.staff)
        response = self.client.post(f"/tickets/events/{self.event.id}/scan/offline/", data=json.dumps({"records": [{"credential": credential}]}), content_type="application/json", HTTP_X_SCANNER_DEVICE=self.device.device_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accepted"], 1)
        batch_id = response.json()["batch_id"]
        reconcile = self.client.post(f"/tickets/scan/offline/{batch_id}/reconcile/")
        self.assertEqual(reconcile.status_code, 200)
        self.assertEqual(reconcile.json()["status"], "reconciled")

    def test_scanner_requires_event_device_and_staff_access(self):
        _, credential = self.issue()
        self.assertEqual(admit_ticket(credential=credential, event=self.event, user=self.owner, device_id=self.device.device_id)[1], "unauthorised")
        self.device.active = False
        self.device.save(update_fields=["active"])
        self.assertEqual(admit_ticket(credential=credential, event=self.event, user=self.staff, device_id=self.device.device_id)[1], "unauthorised")

    def test_public_verification_exposes_no_attendee_data(self):
        _, credential = self.issue()
        response = self.client.get("/tickets/verify/", {"credential": credential})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "valid")
        self.assertNotIn("Private Attendee", response.content.decode())
        self.assertNotIn("owner", response.json())

    def test_customer_wallet_and_qr_are_owner_only(self):
        ticket, credential = self.issue()
        self.client.force_login(self.owner)
        wallet_response = self.client.get("/tickets/wallet/")
        self.assertEqual(wallet_response.status_code, 200)
        self.assertContains(wallet_response, ticket.reference)
        qr_response = self.client.get(f"/tickets/wallet/{ticket.pk}/qr.png")
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response["Content-Type"], "image/png")
        self.assertIn("inline", qr_response["Content-Disposition"])
        download_response = self.client.get(f"/tickets/wallet/{ticket.pk}/qr.png?download=1")
        self.assertIn("attachment", download_response["Content-Disposition"])
        with Image.open(BytesIO(download_response.content)) as downloaded_ticket:
            self.assertEqual(downloaded_ticket.size, (800, 1200))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/tickets/wallet/{ticket.pk}/").status_code, 404)

    def test_marketplace_page_is_public(self):
        response = self.client.get(reverse("ticketing:marketplace"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ticket marketplace")

    def test_verification_and_scanner_pages_are_available_to_the_right_users(self):
        self.assertEqual(self.client.get(reverse("ticketing:ticket-public-verify-page")).status_code, 200)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("ticketing:ticket-scanner-page", args=[self.event.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verified Night")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("ticketing:ticket-scanner-page", args=[self.event.id])).status_code, 404)

    def test_inventory_dashboard_is_organisation_scoped_and_reports_ga_sales(self):
        category = TicketCategory.objects.create(event=self.event, name="General", price_minor=2500, total_quantity=10)
        Ticket.objects.create(event=self.event, owner=self.owner, reference="GA-SOLD-1", ticket_category=category, payment_verified_at=timezone.now())
        snapshot = inventory_snapshot(self.event)
        self.assertEqual(snapshot["general_admission"][0]["sold"], 1)
        self.assertEqual(snapshot["general_admission"][0]["available"], 9)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("ticketing:inventory-dashboard", args=[self.event.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live inventory")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("ticketing:inventory-data", args=[self.event.id])).status_code, 404)

    def test_ticket_category_management_page_renders_category_actions(self):
        category = TicketCategory.objects.create(
            event=self.event, name="General", price_minor=2500, total_quantity=10
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("ticketing:ticket-category-list", args=[self.event.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("ticketing:ticket-category-update", args=[category.pk]))
        self.assertContains(response, reverse("ticketing:ticket-category-delete", args=[category.pk]))

    def test_ticket_category_form_accepts_maloti_and_stores_minor_units(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("ticketing:ticket-category-create", args=[self.event.id]),
            {
                "name": "VIP",
                "description": "",
                "price_maloti": "150.50",
                "total_quantity": "25",
                "max_per_customer": "2",
                "sales_opens_at": "",
                "sales_closes_at": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TicketCategory.objects.get(name="VIP").price_minor, 15050)

    def test_event_can_be_unpublished_and_completed_through_lifecycle_actions(self):
        self.client.force_login(self.staff)
        unpublished = self.client.post(reverse("ticketing:event-unpublish", args=[self.event.pk]))
        self.assertEqual(unpublished.status_code, 302)
        self.assertEqual(Event.objects.get(pk=self.event.pk).status, Event.Status.DRAFT)

        self.event.status = Event.Status.SALES_OPEN
        self.event.starts_at = timezone.now() - timedelta(hours=2)
        self.event.save(update_fields=["status", "starts_at"])
        completed = self.client.post(reverse("ticketing:event-complete", args=[self.event.pk]))
        self.assertEqual(completed.status_code, 302)
        self.assertEqual(Event.objects.get(pk=self.event.pk).status, Event.Status.COMPLETED)


class EventCreationPricingTests(TestCase):
    def setUp(self):
        self.organiser = User.objects.create_user(
            email="organiser@example.com", password="pass-12345"
        )
        self.organisation = Organisation.objects.create(
            name="Pricing Events", slug="pricing-events"
        )
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.organiser,
            role=OrganisationMembership.Role.OWNER,
        )

    def test_event_creation_creates_initial_ticket_category_from_price(self):
        self.client.force_login(self.organiser)
        starts_at = timezone.now() + timedelta(days=30)
        response = self.client.post(
            reverse("ticketing:event-create"),
            {
                "name": "Summer Showcase",
                "description": "A ticketed event.",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
                "sales_opens_at": "",
                "sales_closes_at": "",
                "timezone": "Africa/Maseru",
                "ticketing_model": Event.TicketingModel.GENERAL_ADMISSION,
                "admission_policy": "single_entry",
                "refund_policy": "",
                "resale_policy": "",
                "status": Event.Status.DRAFT,
                "cover_image": "",
                "venue_name": "Maseru Hall",
                "venue_address_line_1": "1 Main Street",
                "venue_address_line_2": "",
                "venue_city": "Maseru",
                "ticket_name": "Early bird",
                "ticket_price_maloti": "125.50",
                "ticket_quantity": "100",
                "ticket_max_per_customer": "4",
            },
        )

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(name="Summer Showcase")
        category = event.ticket_categories.get()
        self.assertEqual(category.name, "Early bird")
        self.assertEqual(category.price_minor, 12550)
        self.assertEqual(category.total_quantity, 100)
        self.assertEqual(category.max_per_customer, 4)

    def test_reserved_event_creates_seating_link_and_default_seats(self):
        self.client.force_login(self.organiser)
        starts_at = timezone.now() + timedelta(days=30)
        response = self.client.post(
            reverse("ticketing:event-create"),
            {
                "name": "Reserved Showcase",
                "description": "A seated event.",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": "",
                "sales_opens_at": "",
                "sales_closes_at": "",
                "timezone": "Africa/Maseru",
                "ticketing_model": Event.TicketingModel.RESERVED_SEATING,
                "admission_policy": "single_entry",
                "refund_policy": "",
                "resale_policy": "",
                "status": Event.Status.DRAFT,
                "cover_image": "",
                "venue_name": "Maseru Theatre",
                "venue_address_line_1": "2 Main Street",
                "venue_address_line_2": "",
                "venue_city": "Maseru",
                "ticket_name": "Standard seat",
                "ticket_price_maloti": "250.00",
                "ticket_quantity": "999",
                "ticket_max_per_customer": "2",
                "seating_rows": "3",
                "seats_per_row": "4",
            },
        )

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(name="Reserved Showcase")
        self.assertTrue(EventSeating.objects.filter(event=event, venue=event.venue).exists())
        self.assertEqual(Seat.objects.filter(row__section__venue=event.venue).count(), 12)
        self.assertEqual(event.ticket_categories.get().total_quantity, 12)
