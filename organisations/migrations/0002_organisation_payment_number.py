from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organisations", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="organisation",
            name="payment_number",
            field=models.CharField(blank=True, help_text="M-Pesa, EcoCash or merchant number customers should pay.", max_length=80),
        ),
    ]
