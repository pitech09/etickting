from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_inventoryhold"),
        ("seating", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="seat_reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="order_lines",
                to="seating.seatreservation",
            ),
        ),
    ]
