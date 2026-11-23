from django.db import migrations, models


def move_legacy_cover_urls(apps, schema_editor):
    Event = apps.get_model("ticketing", "Event")
    for event in Event.objects.exclude(cover_image="").iterator():
        raw_value = event.cover_image.name if event.cover_image else ""
        normalised = raw_value.replace("\\", "")
        if normalised.startswith("https:/") and not normalised.startswith("https://"):
            normalised = normalised.replace("https:/", "https://", 1)
        elif normalised.startswith("http:/") and not normalised.startswith("http://"):
            normalised = normalised.replace("http:/", "http://", 1)
        if normalised.startswith(("http://", "https://")):
            event.cover_image_url = normalised
        event.cover_image = ""
        event.save(update_fields=["cover_image", "cover_image_url"])


class Migration(migrations.Migration):

    dependencies = [
        ("ticketing", "0009_event_cover_image_upload"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="cover_image_url",
            field=models.URLField(
                blank=True,
                help_text="Legacy external cover image URL, retained for compatibility.",
            ),
        ),
        migrations.RunPython(move_legacy_cover_urls, migrations.RunPython.noop),
    ]
