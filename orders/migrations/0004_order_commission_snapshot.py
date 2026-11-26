from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_orderline_seat_reservation")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="commission_rate",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="commission_minor",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="order",
            name="provider_cost_minor",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="order",
            name="organiser_net_minor",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
