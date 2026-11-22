from django.test import TestCase

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
