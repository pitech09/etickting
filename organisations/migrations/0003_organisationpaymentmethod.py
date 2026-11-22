from django.db import migrations, models
import django.db.models.deletion
import uuid


def copy_legacy_payment_numbers(apps, schema_editor):
    Organisation = apps.get_model("organisations", "Organisation")
    OrganisationPaymentMethod = apps.get_model("organisations", "OrganisationPaymentMethod")
    for organisation in Organisation.objects.exclude(payment_number=""):
        OrganisationPaymentMethod.objects.get_or_create(
            organisation_id=organisation.pk,
            account_number=organisation.payment_number,
            defaults={
                "provider": "other",
                "label": "Primary payment number",
            },
        )


class Migration(migrations.Migration):
    dependencies = [("organisations", "0002_organisation_payment_number")]

    operations = [
        migrations.CreateModel(
            name="OrganisationPaymentMethod",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider", models.CharField(choices=[("mpesa", "M-Pesa"), ("ecocash", "EcoCash"), ("bank", "Bank transfer"), ("other", "Other")], max_length=20)),
                ("label", models.CharField(help_text="Short name customers will recognise", max_length=100)),
                ("account_number", models.CharField(help_text="Number, merchant code or account identifier", max_length=120)),
                ("instructions", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organisation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payment_methods", to="organisations.organisation")),
            ],
            options={"ordering": ("sort_order", "label")},
        ),
        migrations.RunPython(copy_legacy_payment_numbers, migrations.RunPython.noop),
    ]
