"""Populate StyleSheet records with CSS content migrated from frontend source files.

Loads initial data from the migration-owned stylesheets.json snapshot, which
contains 14 stylesheet groups covering all frontend CSS files that were
migrated to backend management.
"""

import json
from pathlib import Path

from django.db import migrations


def populate_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    data_path = Path(__file__).resolve().parent / "data" / "stylesheets.json"
    if not data_path.exists():
        return

    with open(data_path) as f:
        records = json.load(f)

    for record in records:
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


def reverse_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")
    StyleSheet.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0003_stylesheet_cmspage_page_css_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_stylesheets, reverse_stylesheets),
    ]
