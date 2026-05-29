from django.db import migrations, models
from django.db.models import Count


def keep_earliest_checkin_record(apps, schema_editor):
    CheckInRecord = apps.get_model("event", "CheckInRecord")

    duplicate_groups = (
        CheckInRecord.objects.values("registration_id").annotate(record_count=Count("id")).filter(record_count__gt=1)
    )
    for group in duplicate_groups:
        records = CheckInRecord.objects.filter(registration_id=group["registration_id"]).order_by("created_at", "id")
        keep = records.first()
        if keep is None:
            continue
        records.exclude(pk=keep.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0003_add_schedule_sync_log"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="checkinrecord",
            name="unique_checkin_per_registration",
        ),
        migrations.RunPython(keep_earliest_checkin_record, reverse_code=migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="checkinrecord",
            constraint=models.UniqueConstraint(
                fields=("registration",),
                name="unique_checkin_record_per_registration",
            ),
        ),
    ]
