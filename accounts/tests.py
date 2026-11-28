from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from .models import User
from organisations.models import Organisation, OrganisationMembership


class AuthenticationTests(TestCase):
    def test_registration_creates_email_user(self):
        with patch("accounts.views.issue_otp") as issue_otp:
            response = self.client.post(reverse("register"), {"first_name": "Mpho", "last_name": "Mokoena", "email": "MPHO@example.com", "phone_number": "05838173", "password1": "A-strong-passphrase-123", "password2": "A-strong-passphrase-123"})
        self.assertRedirects(response, reverse("phone-verify"))
        user = User.objects.get(email="mpho@example.com")
        self.assertEqual(user.phone_number, "+2665838173")
        issue_otp.assert_called_once()

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_customer_login_goes_to_upcoming_events(self):
        User.objects.create_user(email="customer@example.com", password="pass-12345")
        response = self.client.post(reverse("login"), {"username": "customer@example.com", "password": "pass-12345"})
        self.assertRedirects(response, reverse("public-event-list"))

    def test_organisation_member_login_goes_to_workspace(self):
        user = User.objects.create_user(email="organiser@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Events", slug="events")
        OrganisationMembership.objects.create(organisation=organisation, user=user, role=OrganisationMembership.Role.OWNER)
        response = self.client.post(reverse("login"), {"username": "organiser@example.com", "password": "pass-12345"})
        self.assertRedirects(response, reverse("dashboard"))

    def test_platform_admin_login_goes_to_admin(self):
        User.objects.create_superuser(email="admin@example.com", password="pass-12345")
        response = self.client.post(reverse("login"), {"username": "admin@example.com", "password": "pass-12345"})
        self.assertRedirects(response, reverse("admin:index"))

    def test_organiser_registration_creates_owner_membership(self):
        with patch("accounts.views.issue_otp") as issue_otp:
            response = self.client.post(reverse("register-organiser"), {
                "first_name": "Event", "last_name": "Owner", "email": "owner@example.com",
                "phone_number": "05838174",
                "password1": "A-strong-passphrase-123", "password2": "A-strong-passphrase-123",
                "organisation_name": "Mountain Events", "organisation_description": "Live events",
            })
        self.assertRedirects(response, reverse("phone-verify"))
        issue_otp.assert_called_once()
        user = User.objects.get(email="owner@example.com")
        self.assertTrue(user.organisation_memberships.filter(role="owner", organisation__name="Mountain Events").exists())

    def test_customer_cannot_open_organiser_dashboard(self):
        user = User.objects.create_user(email="customer-only@example.com", password="pass-12345")
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("customer-dashboard"))

    def test_organiser_cannot_open_customer_dashboard(self):
        user = User.objects.create_user(email="organiser-only@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Owner Events", slug="owner-events")
        OrganisationMembership.objects.create(organisation=organisation, user=user, role=OrganisationMembership.Role.OWNER)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("customer-dashboard")), reverse("dashboard"))

    def test_account_phone_change_requests_verification_and_preserves_details(self):
        user = User.objects.create_user(
            email="settings@example.com", password="pass-12345", phone_number="+26650123456"
        )
        self.client.force_login(user)
        with patch("accounts.views.issue_otp") as issue_otp:
            response = self.client.post(reverse("account-settings"), {
                "first_name": "Updated",
                "last_name": "Customer",
                "email": user.email,
                "phone_number": "05838173",
            })

        self.assertRedirects(response, reverse("phone-verify"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated")
        self.assertEqual(user.phone_number, "+2665838173")
        self.assertIsNone(user.phone_verified_at)
        issue_otp.assert_called_once()

    def test_password_change_keeps_current_session_active(self):
        user = User.objects.create_user(email="password-change@example.com", password="Old-passphrase-123")
        self.client.force_login(user)

        response = self.client.post(reverse("account-settings"), {
            "action": "password",
            "old_password": "Old-passphrase-123",
            "new_password1": "New-passphrase-456",
            "new_password2": "New-passphrase-456",
        })

        self.assertRedirects(response, reverse("account-settings"))
        self.assertEqual(self.client.get(reverse("account-settings")).status_code, 200)

    def test_phone_change_is_not_saved_when_sms_delivery_fails(self):
        user = User.objects.create_user(
            email="sms-failure@example.com", password="pass-12345", phone_number="+26650123456"
        )
        self.client.force_login(user)

        with patch("accounts.views.issue_otp", side_effect=ValueError("SMS delivery is temporarily unavailable.")):
            response = self.client.post(reverse("account-settings"), {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone_number": "05838173",
            })

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.phone_number, "+26650123456")
        self.assertContains(response, "SMS delivery is temporarily unavailable.")
