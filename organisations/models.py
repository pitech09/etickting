import uuid

from django.conf import settings
from django.db import models


class Organisation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=190, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class OrganisationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        EVENT_MANAGER = "event_manager", "Event manager"
        EVENT_STAFF = "event_staff", "Event staff"

    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organisation_memberships")
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.EVENT_STAFF)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organisation", "user"), name="unique_organisation_member")]

    def __str__(self):
        return f"{self.user} - {self.organisation} ({self.role})"

    def can_manage(self):
        return self.role in {self.Role.OWNER, self.Role.EVENT_MANAGER}
