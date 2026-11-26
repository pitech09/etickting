from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ticketing", "0010_event_cover_image_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanattempt",
            name="kind",
            field=models.CharField(
                choices=[("verification", "Verification"), ("admission", "Admission")],
                default="admission",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="admission",
            name="gate",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="admission",
            name="device",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="admissions",
                to="ticketing.scannerdevice",
            ),
        ),
    ]
