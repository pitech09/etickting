from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ticketing", "0011_admission_scan_metadata"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scanattempt",
            name="result",
            field=models.CharField(
                choices=[
                    ("valid", "Valid"),
                    ("verified", "Verified"),
                    ("invalid", "Invalid"),
                    ("used", "Already used"),
                    ("unauthorised", "Unauthorised"),
                ],
                max_length=20,
            ),
        ),
    ]
