from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


class HealthTests(SimpleTestCase):
    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SUPPORT_EMAIL="kena.support@gmail.com")
class PublicInformationTests(TestCase):
    def test_public_policy_pages_and_contact_page_are_available(self):
        for name in ("customer-terms", "organiser-terms", "contact"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_contact_form_emails_support(self):
        response = self.client.post(reverse("contact"), {
            "name": "Mpho",
            "email": "customer@example.com",
            "subject": "Order help",
            "message": "Please help with my order.",
            "website": "",
        })
        self.assertRedirects(response, reverse("contact"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["kena.support@gmail.com"])
