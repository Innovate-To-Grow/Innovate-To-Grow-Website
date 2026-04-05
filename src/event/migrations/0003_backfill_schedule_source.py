"""Copy schedule import fields from Event to EventScheduleSource."""

from django.db import migrations


def backfill_schedule_source(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    EventScheduleSource = apps.get_model("event", "EventScheduleSource")

    for event in Event.objects.all():
        has_data = event.schedule_sheet_id or event.schedule_tracks_gid or event.schedule_projects_gid
        has_sync = event.schedule_last_synced_at or event.schedule_sync_error
        if has_data or has_sync:
            EventScheduleSource.objects.create(
                event=event,
                sheet_id=event.schedule_sheet_id,
                tracks_gid=event.schedule_tracks_gid,
                projects_gid=event.schedule_projects_gid,
                last_synced_at=event.schedule_last_synced_at,
                sync_error=event.schedule_sync_error,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0002_create_schedule_source"),
    ]

    operations = [
        migrations.RunPython(backfill_schedule_source, migrations.RunPython.noop),
    ]
