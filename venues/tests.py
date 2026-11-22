from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from organisations.models import Organisation, OrganisationMembership

from .models import Venue


class VenueTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="manager@example.com", password="test-pass-123"
        )
        self.other = User.objects.create_user(
            email="outsider@example.com", password="test-pass-123"
        )
        self.organisation = Organisation.objects.create(
            name="Maseru Events", slug="maseru-events"
        )
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.user,
            role=OrganisationMembership.Role.EVENT_MANAGER,
        )

    def test_user_can_create_venue_in_own_organisation(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("venue-create"),
            {
                "organisation": self.organisation.pk,
                "name": "Maseru Hall",
                "slug": "maseru-hall",
                "city": "Maseru",
                "country": "Lesotho",
                "capacity": 500,
            },
        )
        self.assertRedirects(response, reverse("venue-list"))
        self.assertTrue(
            Venue.objects.filter(name="Maseru Hall", organisation=self.organisation).exists()
        )

    def test_user_cannot_see_venues_from_other_organisation(self):
        other_org = Organisation.objects.create(
            name="Other Events", slug="other-events"
        )
        OrganisationMembership.objects.create(
            organisation=other_org, user=self.other, role=OrganisationMembership.Role.OWNER
        )
        Venue.objects.create(
            organisation=other_org, name="Other Hall", slug="other-hall", city="Maseru"
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("venue-list"))
        self.assertNotContains(response, "Other Hall")

    def test_user_cannot_edit_venue_from_other_organisation(self):
        venue = Venue.objects.create(
            organisation=self.organisation,
            name="Maseru Hall",
            slug="maseru-hall",
            city="Maseru",
        )
        self.client.force_login(self.other)
        response = self.client.get(
            reverse("venue-update", args=[venue.pk])
        )
        self.assertEqual(response.status_code, 403)