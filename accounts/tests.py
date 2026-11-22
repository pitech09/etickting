from django.test import TestCase
from django.urls import reverse

from .models import User


class AuthenticationTests(TestCase):
    def test_registration_creates_email_user(self):
        response = self.client.post(reverse("register"), {"first_name": "Mpho", "last_name": "Mokoena", "email": "MPHO@example.com", "password1": "A-strong-passphrase-123", "password2": "A-strong-passphrase-123"})
        self.assertRedirects(response, reverse("login"))
        self.assertTrue(User.objects.filter(email="mpho@example.com").exists())

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")
