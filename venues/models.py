import uuid

from django.conf import settings
from django.db import models


class Venue(models.Model):
    """A physical venue that can host one or more events.

    Venues belong to an organisation and are reusable across multiple events.
    The physical layout (sections, rows, seats) is managed separately in the
    seating application, keeping venue definition distinct from event-specific
    seat availability and pricing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.CASCADE,
        related_name="venues",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=190)
    description = models.TextField(blank=True)
    address_line_1 = models.CharField(max_length=200, blank=True)
    address_line_2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Lesotho")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("organisation", "slug"),
                name="unique_venue_slug_per_organisation",
            ),
        ]

    def __str__(self):
        return self.name