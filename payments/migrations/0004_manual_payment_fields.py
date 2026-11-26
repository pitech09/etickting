from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("payments", "0003_payment_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="received_amount_minor",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Amount confirmed against the mobile money transaction by a reviewer",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="sender_phone",
            field=models.CharField(
                blank=True,
                help_text="Customer mobile number used to make a manual payment",
                max_length=40,
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(provider_reference__isnull=False) & ~models.Q(provider_reference=""),
                fields=("provider", "provider_reference"),
                name="unique_provider_transaction_reference",
            ),
        ),
        migrations.CreateModel(
            name="PaymentReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision", models.CharField(choices=[("approved", "Approved"), ("rejected", "Rejected")], max_length=20)),
                ("previous_status", models.CharField(max_length=20)),
                ("resulting_status", models.CharField(max_length=20)),
                ("received_amount_minor", models.PositiveIntegerField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="review_history", to="payments.payment")),
                ("reviewer", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
