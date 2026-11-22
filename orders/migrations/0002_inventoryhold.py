from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="InventoryHold",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity", models.PositiveIntegerField()),
                ("session_key", models.CharField(blank=True, max_length=200)),
                ("expires_at", models.DateTimeField()),
                ("status", models.CharField(choices=[("active", "Active"), ("expired", "Expired"), ("released", "Released"), ("converted", "Converted to tickets")], default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_holds", to="orders.order")),
                ("ticket_category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_holds", to="ticketing.ticketcategory")),
            ],
        ),
        migrations.AddIndex(
            model_name="inventoryhold",
            index=models.Index(fields=["ticket_category", "status", "expires_at"], name="orders_inve_ticket__57b19f_idx"),
        ),
    ]
