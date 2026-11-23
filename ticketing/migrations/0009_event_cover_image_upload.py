from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ticketing", "0008_ticket_order"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="cover_image",
            field=models.ImageField(
                blank=True,
                help_text="Optional event cover image (JPEG, PNG or WebP; maximum 10 MB).",
                upload_to="event-covers/",
            ),
        ),
    ]
