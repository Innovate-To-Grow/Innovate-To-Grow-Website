from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0003_backfill_schedule_source"),
    ]

    operations = [
        migrations.RemoveField(model_name="event", name="schedule_sheet_id"),
        migrations.RemoveField(model_name="event", name="schedule_tracks_gid"),
        migrations.RemoveField(model_name="event", name="schedule_projects_gid"),
        migrations.RemoveField(model_name="event", name="schedule_last_synced_at"),
        migrations.RemoveField(model_name="event", name="schedule_sync_error"),
    ]
