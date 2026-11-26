from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_order_commission_snapshot")]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="fee_minor",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Legacy customer service fee snapshot; new orders keep this at zero",
            ),
        ),
    ]
