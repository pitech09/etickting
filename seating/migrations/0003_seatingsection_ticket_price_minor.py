from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("seating", "0002_alter_seatingsection_price_modifier_minor"),
    ]

    operations = [
        migrations.AddField(
            model_name="seatingsection",
            name="ticket_price_minor",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                help_text="Optional section ticket price in Maloti. Blank uses the event ticket category price.",
                max_digits=12,
                null=True,
            ),
        ),
    ]
