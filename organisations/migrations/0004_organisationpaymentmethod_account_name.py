from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organisations", "0003_organisationpaymentmethod")]

    operations = [
        migrations.AddField(
            model_name="organisationpaymentmethod",
            name="account_name",
            field=models.CharField(
                blank=True,
                help_text="The registered name shown to customers for this payment destination",
                max_length=180,
            ),
        ),
    ]
