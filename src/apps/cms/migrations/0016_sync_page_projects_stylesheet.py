"""Re-sync the ``page-projects`` stylesheet from the JSON snapshot.

0004 seeds stylesheets via ``update_or_create(name=...)`` and only runs once, so
edits to ``data/stylesheets.json`` do not reach already-migrated databases. This
migration re-applies just the ``page-projects`` entry so the new past-project
share note styles land on existing environments too. It is idempotent and scoped
to a single stylesheet name.
"""

import json
from pathlib import Path

from django.db import migrations

STYLESHEET_NAME = "page-projects"


def sync_page_projects(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    data_path = Path(__file__).resolve().parent / "data" / "stylesheets.json"
    if not data_path.exists():
        return

    with open(data_path) as f:
        records = json.load(f)

    record = next((r for r in records if r["fields"]["name"] == STYLESHEET_NAME), None)
    if record is None:
        return

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
        ("cms", "0015_cmsembedwidget_schedule"),
    ]

    operations = [
        migrations.RunPython(sync_page_projects, noop_reverse),
    ]
