"""Populate StyleSheet records with CSS content migrated from frontend source files.

Loads initial data from cms/fixtures/stylesheets.json which contains 15 stylesheet
groups covering all 73 frontend CSS files that were migrated to backend management.
"""

import json
from pathlib import Path

from django.db import migrations


def populate_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "stylesheets.json"
    if not fixture_path.exists():
        return

    with open(fixture_path) as f:
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
