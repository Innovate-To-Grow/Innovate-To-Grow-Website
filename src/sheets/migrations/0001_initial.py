"""Move GoogleSheetSource from pages app to sheets app.

Uses SeparateDatabaseAndState to rename the DB table and transfer the model
to the sheets app state without losing data.
"""

import uuid

from django.db import migrations, models


def update_content_type(apps, schema_editor):
    """Update django_content_type row from pages to sheets."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="pages", model="googlesheetsource").update(app_label="sheets")


def revert_content_type(apps, schema_editor):
    """Revert django_content_type row from sheets to pages."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="sheets", model="googlesheetsource").update(app_label="pages")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("pages", "0016_sitesettings_homepage_page"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="GoogleSheetSource",
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
                        ("version", models.PositiveIntegerField(default=0, editable=False)),
                        (
                            "slug",
                            models.SlugField(
                                help_text="API lookup key, e.g. 'current-event', '2025-fall'",
                                unique=True,
                            ),
                        ),
                        ("title", models.CharField(help_text="Display name", max_length=200)),
                        (
                            "sheet_type",
                            models.CharField(
                                choices=[
                                    ("current-event", "Current Event"),
                                    ("past-projects", "Past Projects"),
                                    ("archive-event", "Archive Event"),
                                ],
                                help_text="Controls parsing logic",
                                max_length=20,
                            ),
                        ),
                        (
                            "spreadsheet_id",
                            models.CharField(help_text="Google Sheets spreadsheet ID", max_length=200),
                        ),
                        (
                            "range_a1",
                            models.CharField(
                                help_text="Sheet range, e.g. 'A1:Y76' or 'Past-Projects-WEB-LIVE'",
                                max_length=200,
                            ),
                        ),
                        (
                            "tracks_spreadsheet_id",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="Optional separate spreadsheet for track info",
                                max_length=200,
                            ),
                        ),
                        (
                            "tracks_sheet_name",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="Track info sheet name, e.g. '2025-I2G2-Tracks'",
                                max_length=200,
                            ),
                        ),
                        (
                            "semester_filter",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="Optional row filter, e.g. '2025-2 Fall'",
                                max_length=100,
                            ),
                        ),
                        (
                            "cache_ttl_seconds",
                            models.PositiveIntegerField(default=300, help_text="Cache TTL in seconds"),
                        ),
                        ("is_active", models.BooleanField(default=True, help_text="Disable without deleting")),
                    ],
                    options={
                        "verbose_name": "Sheet Source",
                        "verbose_name_plural": "Sheet Sources",
                        "ordering": ["slug"],
                        "abstract": False,
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "pages_googlesheetsource" RENAME TO "sheets_googlesheetsource"',
                    reverse_sql='ALTER TABLE "sheets_googlesheetsource" RENAME TO "pages_googlesheetsource"',
                ),
            ],
        ),
        migrations.RunPython(update_content_type, revert_content_type),
    ]
