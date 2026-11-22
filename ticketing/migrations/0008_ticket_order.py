from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("ticketing", "0007_offlinescanbatch_offlinescanrecord"), ("orders", "0002_inventoryhold")]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="order",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tickets", to="orders.order"),
        ),
    ]
