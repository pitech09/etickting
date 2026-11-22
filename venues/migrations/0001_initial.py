import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organisations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Venue",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=190)),
                ("description", models.TextField(blank=True)),
                ("address_line_1", models.CharField(blank=True, max_length=200)),
                ("address_line_2", models.CharField(blank=True, max_length=200)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("country", models.CharField(default="Lesotho", max_length=100)),
                (
                    "capacity",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organisation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="venues",
                        to="organisations.organisation",
                    ),
                ),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.AddConstraint(
            model_name="venue",
            constraint=models.UniqueConstraint(
                fields=("organisation", "slug"),
                name="unique_venue_slug_per_organisation",
            ),
        ),
    ]