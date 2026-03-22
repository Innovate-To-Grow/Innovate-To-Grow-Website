"""Migrate GoogleSheetSource from plain Model to ProjectControlModel.

Swaps the integer PK to UUID and adds soft-delete/versioning fields.
No other models reference GoogleSheetSource by FK, so this is safe.
"""

import uuid

from django.db import migrations, models


def populate_uuids(apps, schema_editor):
    """Assign a UUID to every existing row."""
    GoogleSheetSource = apps.get_model("pages", "GoogleSheetSource")
    for row in GoogleSheetSource.objects.all():
        row.new_id = uuid.uuid4()
        row.save(update_fields=["new_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("pages", "0012_menu_is_active"),
    ]

    operations = [
        # 1. Add ProjectControlModel fields (except id — handled separately)
        migrations.AddField(
            model_name="googlesheetsource",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True, default="2026-01-01T00:00:00Z"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="googlesheetsource",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddField(
            model_name="googlesheetsource",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="googlesheetsource",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="googlesheetsource",
            name="version",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        # 2. Add a temporary UUID column
        migrations.AddField(
            model_name="googlesheetsource",
            name="new_id",
            field=models.UUIDField(default=uuid.uuid4, null=True),
        ),
        # 3. Populate UUIDs for existing rows
        migrations.RunPython(populate_uuids, migrations.RunPython.noop),
        # 4. Remove the old integer PK
        migrations.RemoveField(
            model_name="googlesheetsource",
            name="id",
        ),
        # 5. Rename new_id → id and set as primary key
        migrations.RenameField(
            model_name="googlesheetsource",
            old_name="new_id",
            new_name="id",
        ),
        migrations.AlterField(
            model_name="googlesheetsource",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
            ),
        ),
    ]
