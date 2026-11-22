import uuid

from django.conf import settings
from django.db import models


class Organisation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=190, unique=True)
    description = models.TextField(blank=True)
    payment_number = models.CharField(
        max_length=80,
        blank=True,
        help_text="M-Pesa, EcoCash or merchant number customers should pay.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class OrganisationPaymentMethod(models.Model):
    class Provider(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        ECOCASH = "ecocash", "EcoCash"
        BANK = "bank", "Bank transfer"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation, on_delete=models.CASCADE, related_name="payment_methods"
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    label = models.CharField(max_length=100, help_text="Short name customers will recognise")
    account_number = models.CharField(max_length=120, help_text="Number, merchant code or account identifier")
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "label")

    def __str__(self):
        return f"{self.organisation.name} — {self.label}"


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
