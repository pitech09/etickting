import base64
import json
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation, OrganisationMembership

from .models import Admission, Event, ResaleListing, ScanAttempt, ScannerDevice, Ticket, TicketCredential
from .services import admit_ticket, create_resale_listing, issue_ticket, purchase_resale, transfer_ticket, verify_credential


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

    def test_verification_and_scanner_pages_are_available_to_the_right_users(self):
        self.assertEqual(self.client.get(reverse("ticketing:ticket-public-verify-page")).status_code, 200)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("ticketing:ticket-scanner-page", args=[self.event.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verified Night")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("ticketing:ticket-scanner-page", args=[self.event.id])).status_code, 404)
