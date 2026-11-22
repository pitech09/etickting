from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("organisations", "0003_organisationpaymentmethod"),
        ("payments", "0002_manual_payment_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="payment_method",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="organisations.organisationpaymentmethod"),
        ),
        migrations.AlterField(
            model_name="payment",
            name="provider",
            field=models.CharField(choices=[("mpesa", "M-Pesa"), ("ecocash", "EcoCash"), ("bank", "Bank transfer"), ("other", "Other"), ("sandbox", "Sandbox (development)")], max_length=20),
        ),
    ]
