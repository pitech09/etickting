from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .models import Organisation, OrganisationMembership
from ticketing.models import Event, ScannerDevice


class OrganisationTests(TestCase):
    def test_membership_is_unique_and_role_is_manageable(self):
        user = User.objects.create_user(email="owner@example.com", password="test-pass-123")
        organisation = Organisation.objects.create(name="Maseru Events", slug="maseru-events")
        membership = OrganisationMembership.objects.create(organisation=organisation, user=user, role=OrganisationMembership.Role.OWNER)
        self.assertTrue(membership.can_manage())
        with self.assertRaises(Exception):
            OrganisationMembership.objects.create(organisation=organisation, user=user)

    def test_user_can_create_organisation_and_becomes_owner(self):
        user = User.objects.create_user(email="creator@example.com", password="pass-12345")
        self.client.force_login(user)
        response = self.client.post(
            reverse("organisations:create"),
            {"name": "Maseru Live", "description": "Local events"},
        )
        organisation = Organisation.objects.get(name="Maseru Live")
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(
            OrganisationMembership.objects.filter(
                organisation=organisation,
                user=user,
                role=OrganisationMembership.Role.OWNER,
            ).exists()
        )

    def test_owner_can_add_team_member_and_scanner_device(self):
        owner = User.objects.create_user(email="owner@example.com", password="test-pass-123")
        staff = User.objects.create_user(email="staff@example.com", password="test-pass-123")
        organisation = Organisation.objects.create(name="Entry Events", slug="entry-events")
        OrganisationMembership.objects.create(
            organisation=organisation, user=owner, role=OrganisationMembership.Role.OWNER
        )
        event = Event.objects.create(
            organisation=organisation,
            name="Entry Night",
            starts_at=timezone.now(),
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("organisations:member-add", args=[organisation.id]),
            {
                "first_name": "Staff",
                "last_name": "Member",
                "email": staff.email,
                "password": "Temporary-pass-123",
                "role": OrganisationMembership.Role.EVENT_STAFF,
            },
        )
        self.assertRedirects(response, f'{reverse("organisations:edit", args=[organisation.id])}?tab=team')
        membership = OrganisationMembership.objects.get(organisation=organisation, user=staff)
        self.assertEqual(membership.role, OrganisationMembership.Role.EVENT_STAFF)

        response = self.client.post(
            reverse("organisations:device-create", args=[organisation.id]),
            {"device_id": "entrance-phone-1", "event": event.id, "user": staff.id, "active": "on"},
        )
        self.assertRedirects(response, f'{reverse("organisations:edit", args=[organisation.id])}?tab=devices')
        self.assertTrue(ScannerDevice.objects.filter(device_id="entrance-phone-1", user=staff).exists())

    def test_non_owner_cannot_manage_members_or_devices(self):
        owner = User.objects.create_user(email="owner@example.com", password="test-pass-123")
        manager = User.objects.create_user(email="manager@example.com", password="test-pass-123")
        organisation = Organisation.objects.create(name="Managed Events", slug="managed-events")
        OrganisationMembership.objects.create(
            organisation=organisation, user=owner, role=OrganisationMembership.Role.OWNER
        )
        OrganisationMembership.objects.create(
            organisation=organisation, user=manager, role=OrganisationMembership.Role.EVENT_MANAGER
        )
        self.client.force_login(manager)
        response = self.client.post(
            reverse("organisations:member-add", args=[organisation.id]),
            {"email": "nobody@example.com", "role": OrganisationMembership.Role.EVENT_STAFF},
        )
        self.assertEqual(response.status_code, 404)
