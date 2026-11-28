from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog
from organisations.models import Organisation, OrganisationMembership
from venues.models import Venue

from .models import Seat, SeatingRow, SeatingSection


class SeatingSectionPricingTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email="manager@example.com", password="pass-12345")
        organisation = Organisation.objects.create(name="Pricing Org", slug="pricing-org")
        OrganisationMembership.objects.create(
            organisation=organisation,
            user=self.manager,
            role=OrganisationMembership.Role.EVENT_MANAGER,
        )
        self.venue = Venue.objects.create(organisation=organisation, name="Pricing Hall", slug="pricing-hall")

    def test_manager_can_create_and_edit_section_price_and_audit_change(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("seating:section-create", args=[self.venue.pk]),
            {
                "name": "VIP",
                "description": "Front rows",
                "color": "#111111",
                "ticket_price_minor": "500.00",
                "price_modifier_minor": "0.00",
                "is_accessible": "on",
                "sort_order": "1",
            },
        )
        self.assertRedirects(response, reverse("seating:section-list", args=[self.venue.pk]))
        section = SeatingSection.objects.get(name="VIP")
        self.assertEqual(section.ticket_price_minor, Decimal("500.00"))
        self.assertEqual(AuditLog.objects.filter(action="seating_section_created").count(), 1)

        row = SeatingRow.objects.create(section=section, name="A")
        Seat.objects.create(row=row, number="1", label="A-1")
        response = self.client.post(
            reverse("seating:section-update", args=[section.pk]),
            {
                "name": "VIP",
                "description": "Front rows",
                "color": "#111111",
                "ticket_price_minor": "550.00",
                "price_modifier_minor": "0.00",
                "sort_order": "1",
            },
        )
        self.assertRedirects(response, reverse("seating:section-list", args=[self.venue.pk]))
        section.refresh_from_db()
        self.assertEqual(section.ticket_price_minor, Decimal("550.00"))
        self.assertEqual(section.seat_count, 1)
        self.assertEqual(section.potential_revenue_minor, Decimal("550.00"))
        self.assertEqual(AuditLog.objects.filter(action="seating_section_price_changed").count(), 1)

    def test_section_price_rejects_negative_values_and_allows_free_sections(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("seating:section-create", args=[self.venue.pk]),
            {
                "name": "General",
                "color": "#222222",
                "ticket_price_minor": "-1.00",
                "price_modifier_minor": "0.00",
                "sort_order": "2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value is greater than or equal to 0")
        self.assertFalse(SeatingSection.objects.filter(name="General").exists())

        response = self.client.post(
            reverse("seating:section-create", args=[self.venue.pk]),
            {
                "name": "Free area",
                "color": "#222222",
                "ticket_price_minor": "0.00",
                "price_modifier_minor": "0.00",
                "sort_order": "3",
            },
        )
        self.assertRedirects(response, reverse("seating:section-list", args=[self.venue.pk]))
        self.assertEqual(SeatingSection.objects.get(name="Free area").ticket_price_minor, Decimal("0.00"))
