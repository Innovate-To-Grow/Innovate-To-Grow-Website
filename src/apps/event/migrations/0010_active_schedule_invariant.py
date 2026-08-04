from django.db import migrations, models


def normalize_active_schedule(apps, schema_editor):
    Schedule = apps.get_model("event", "CurrentProjectSchedule")
    # The pre-migration loader used ``filter(...).first()`` with no model
    # ordering, so Django selected the lowest primary key. Preserve that exact
    # runtime winner once before adding the uniqueness constraint.
    active = Schedule.objects.filter(is_active=True).order_by("pk")
    keep = active.first()
    if keep is not None:
        active.exclude(pk=keep.pk).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0009_registration_sheet_sync_audit"),
    ]

    operations = [
        migrations.RunPython(normalize_active_schedule, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="currentprojectschedule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("is_active",),
                name="event_one_active_schedule",
            ),
        ),
    ]
