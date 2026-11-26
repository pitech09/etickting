from django.test import TestCase
from django.urls import reverse

from .models import User
from organisations.models import Organisation, OrganisationMembership


class AuthenticationTests(TestCase):
    def test_registration_creates_email_user(self):
        response = self.client.post(reverse("register"), {"first_name": "Mpho", "last_name": "Mokoena", "email": "MPHO@example.com", "password1": "A-strong-passphrase-123", "password2": "A-strong-passphrase-123"})
        self.assertRedirects(response, reverse("login"))
        self.assertTrue(User.objects.filter(email="mpho@example.com").exists())

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
        response = self.client.post(reverse("register-organiser"), {
            "first_name": "Event", "last_name": "Owner", "email": "owner@example.com",
            "password1": "A-strong-passphrase-123", "password2": "A-strong-passphrase-123",
            "organisation_name": "Mountain Events", "organisation_description": "Live events",
        })
        self.assertRedirects(response, reverse("login"))
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
