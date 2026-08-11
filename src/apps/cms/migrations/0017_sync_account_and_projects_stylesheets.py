"""Re-sync the ``auth`` and ``page-projects`` stylesheets from the JSON snapshot.

0004 seeds stylesheets via ``update_or_create(name=...)`` and only runs once, so
edits to ``data/stylesheets.json`` do not reach already-migrated databases. This
migration re-applies the two entries touched by the share-management feature (the
account "my shared links" styles in ``auth`` and the share-name input style in
``page-projects``) so they land on existing environments too. Idempotent and
scoped to those two stylesheet names.
"""

import json
from pathlib import Path

from django.db import migrations

STYLESHEET_NAMES = ("auth", "page-projects")


def sync_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    data_path = Path(__file__).resolve().parent / "data" / "stylesheets.json"
    if not data_path.exists():
        return

    with open(data_path) as f:
        records = json.load(f)

    for name in STYLESHEET_NAMES:
        record = next((r for r in records if r["fields"]["name"] == name), None)
        if record is None:
            continue
        fields = record["fields"]
        StyleSheet.objects.update_or_create(
            name=fields["name"],
            defaults={
                "display_name": fields["display_name"],
                "description": fields.get("description", ""),
                "css": fields["css"],
                "is_active": fields["is_active"],
                "sort_order": fields["sort_order"],
            },
        )


def noop_reverse(apps, schema_editor):
    # The previous CSS is not retained; reversing is a no-op (forward re-sync is idempotent).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0016_sync_page_projects_stylesheet"),
    ]

    operations = [
        migrations.RunPython(sync_stylesheets, noop_reverse),
    ]
