# Generated migration for adding slug, is_live fields to Event and abstract to Presentation

from django.db import migrations, models
import django.utils.text


def generate_slugs_for_existing_events(apps, schema_editor):
    """Generate slugs for existing events based on event_name."""
    Event = apps.get_model('events', 'Event')
    for event in Event.objects.filter(slug__isnull=True):
        # Generate slug from event_name
        base_slug = django.utils.text.slugify(event.event_name)
        slug = base_slug
        counter = 1
        # Ensure uniqueness
        while Event.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        event.slug = slug
        event.save()


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_event_expo_table_event_reception_table_and_more"),
    ]

    operations = [
        # Add slug as nullable first
        migrations.AddField(
            model_name="event",
            name="slug",
            field=models.SlugField(
                max_length=255,
                null=True,
                unique=True,
                help_text="Unique slug identifier for the event (e.g., 'spring-expo-2026').",
            ),
        ),
        # Add is_live with default
        migrations.AddField(
            model_name="event",
            name="is_live",
            field=models.BooleanField(
                default=False,
                help_text="Whether this event is currently live (only one event can be live at a time).",
            ),
        ),
        # Add abstract to Presentation
        migrations.AddField(
            model_name="presentation",
            name="abstract",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Abstract/project description.",
            ),
        ),
        # Generate slugs for existing events
        migrations.RunPython(generate_slugs_for_existing_events, migrations.RunPython.noop),
        # Make slug non-nullable
        migrations.AlterField(
            model_name="event",
            name="slug",
            field=models.SlugField(
                max_length=255,
                unique=True,
                help_text="Unique slug identifier for the event (e.g., 'spring-expo-2026').",
            ),
        ),
    ]
