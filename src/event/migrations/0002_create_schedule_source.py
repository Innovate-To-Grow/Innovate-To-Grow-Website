import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventScheduleSource",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("sheet_id", models.CharField(blank=True, default="", max_length=255)),
                ("tracks_gid", models.PositiveBigIntegerField(blank=True, null=True)),
                ("projects_gid", models.PositiveBigIntegerField(blank=True, null=True)),
                (
                    "last_synced_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                ("sync_error", models.TextField(blank=True, default="")),
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedule_source",
                        to="event.event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Schedule Import Source",
            },
        ),
    ]
