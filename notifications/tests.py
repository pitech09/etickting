from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import Notification


class NotificationInboxTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="notifications@example.com", password="password")
        self.other = User.objects.create_user(email="other-notifications@example.com", password="password")
        self.client.force_login(self.user)

    def test_unread_notification_can_be_marked_read_and_follow_internal_link(self):
        notification = Notification.objects.create(
            user=self.user,
            title="Ticket ready",
            message="Your ticket is ready.",
            action_url="/tickets/wallet/",
        )

        response = self.client.post(reverse("notifications:mark-read", args=[notification.pk]))

        self.assertRedirects(response, "/tickets/wallet/")
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_mark_all_read_is_scoped_to_current_user(self):
        own = Notification.objects.create(user=self.user, title="Own", message="Own")
        other = Notification.objects.create(user=self.other, title="Other", message="Other")

        response = self.client.post(reverse("notifications:mark-all-read"))

        self.assertRedirects(response, reverse("notifications:inbox"))
        own.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.assertIsNone(other.read_at)

    def test_external_notification_action_links_are_rejected(self):
        from .services import notify

        with self.assertRaises(ValueError):
            notify(user=self.user, title="Unsafe", message="Unsafe", action_url="https://example.com")
