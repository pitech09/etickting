from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="proof_image",
            field=models.ImageField(blank=True, help_text="Customer payment screenshot for manual review", null=True, upload_to="payment-proofs/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="payment",
            name="review_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_payments", to=settings.AUTH_USER_MODEL),
        ),
    ]
