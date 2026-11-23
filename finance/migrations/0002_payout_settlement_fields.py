from django.db import migrations, models
import uuid


def populate_payout_keys(apps, schema_editor):
    Payout = apps.get_model("finance", "Payout")
    for payout in Payout.objects.filter(idempotency_key__isnull=True).iterator():
        payout.idempotency_key = f"legacy-{uuid.uuid4().hex}"
        payout.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [("finance", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="payout",
            name="failure_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="payout",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.RunPython(populate_payout_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="payout",
            name="idempotency_key",
            field=models.CharField(max_length=128, unique=True),
        ),
        migrations.AddField(
            model_name="payout",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payout",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
