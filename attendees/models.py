from django.conf import settings
from django.db import models


class AttendeeProfile(models.Model):
    """Customer-controlled identity details; the photograph is never public."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendee_profile")
    display_name = models.CharField(max_length=180, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    photo = models.ImageField(upload_to="attendee_photos/%Y/%m/", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.user.email
