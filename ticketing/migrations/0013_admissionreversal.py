from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ticketing", "0012_alter_scanattempt_result"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmissionReversal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_device_id", models.CharField(blank=True, max_length=100)),
                ("original_gate", models.CharField(blank=True, max_length=100)),
                ("original_admitted_at", models.DateTimeField()),
                ("original_reentry_count", models.PositiveIntegerField(default=0)),
                ("reason", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="admission_reversals", to="ticketing.event")),
                ("original_admitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="original_admissions_reversed", to=settings.AUTH_USER_MODEL)),
                ("reversed_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="admission_reversals", to="ticketing.ticket")),
            ],
        ),
    ]
