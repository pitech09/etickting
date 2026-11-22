from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from .models import Organisation, OrganisationMembership


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
