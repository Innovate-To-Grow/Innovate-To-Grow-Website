from django.db import migrations, models


def copy_live_events_to_registration_open(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    Event.objects.filter(is_live=True).update(registration_open=True)


def clear_registration_open(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    Event.objects.update(registration_open=False)


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0006_ticket_login_unification"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="registration_open",
            field=models.BooleanField(
                default=False,
                help_text="Allow this event to appear in public registration and accept new registrations.",
                verbose_name="Registration open",
            ),
        ),
        migrations.RunPython(copy_live_events_to_registration_open, clear_registration_open),
    ]
