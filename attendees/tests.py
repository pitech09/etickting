from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class AttendeeProfileTests(TestCase):
    def test_profile_requires_login_and_can_be_saved(self):
        response = self.client.get(reverse("attendee-profile"))
        self.assertEqual(response.status_code, 302)
        user = User.objects.create_user(email="attendee@example.com", password="test-pass-123")
        self.client.force_login(user)
        response = self.client.post(reverse("attendee-profile"), {"display_name": "Mpho", "phone_number": "+26650000000"})
        self.assertRedirects(response, reverse("attendee-profile"))
        self.assertEqual(user.attendee_profile.display_name, "Mpho")
