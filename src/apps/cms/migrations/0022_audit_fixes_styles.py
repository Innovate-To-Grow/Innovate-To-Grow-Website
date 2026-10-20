"""Ship the CMS-managed styles for the production audit fixes.

1. Adds the layout.prose_max_width design token (75ch) to Site Settings where it is missing.
   CMS prose, news stories and app copy cap their line length with it; a value an admin
   already set is kept.
2. Re-syncs the stylesheets this change touched from data/stylesheets.json (readable line
   length, account and subscribe controls, phone header and footer, home page columns). The
   CSS stays CMS-managed: as in 0021, before a sheet's CSS is replaced it is kept as an
   inactive "<name>-pre-audit-fixes" sheet, so an admin can compare it or switch back.

The reverse copies those saved sheets back and drops the token while it still holds the
value added here.
"""

import json
from pathlib import Path

from django.db import migrations

ADDED_TOKENS = {
    "layout": {
        "prose_max_width": "75ch",
    },
}

SYNCED_SHEETS = (
    "global",
    "layout-menu",
    "layout-footer",
    "cms-blocks",
    "cms-pages",
    "auth",
    "page-news",
    "page-subscribe",
)

BACKUP_SUFFIX = "-pre-audit-fixes"


def backup_name(name):
    return f"{name}{BACKUP_SUFFIX}"


def add_tokens(current):
    tokens = {group: dict(values) for group, values in (current or {}).items() if isinstance(values, dict)}
    for group, values in ADDED_TOKENS.items():
        target = tokens.setdefault(group, {})
        for key, value in values.items():
            target.setdefault(key, value)
    return tokens


def remove_tokens(current):
    """Undo add_tokens for every token that still holds the value it added."""
    tokens = {group: dict(values) for group, values in (current or {}).items() if isinstance(values, dict)}
    for group, values in ADDED_TOKENS.items():
        target = tokens.get(group)
        if target is None:
            continue
        for key, value in values.items():
            if target.get(key) == value:
                del target[key]
    return tokens


def update_design_tokens(apps, schema_editor):
    SiteSettings = apps.get_model("cms", "SiteSettings")
    for settings in SiteSettings.objects.all():
        settings.design_tokens = add_tokens(settings.design_tokens)
        settings.save(update_fields=["design_tokens"])


def restore_design_tokens(apps, schema_editor):
    SiteSettings = apps.get_model("cms", "SiteSettings")
    for settings in SiteSettings.objects.all():
        settings.design_tokens = remove_tokens(settings.design_tokens)
        settings.save(update_fields=["design_tokens"])


def load_seed_sheets():
    data_path = Path(__file__).resolve().parent / "data" / "stylesheets.json"
    if not data_path.exists():
        return []
    with open(data_path) as f:
        return [record["fields"] for record in json.load(f) if record["fields"]["name"] in SYNCED_SHEETS]


def sync_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    for fields in load_seed_sheets():
        current = StyleSheet.objects.filter(name=fields["name"]).first()
        if current is not None and current.css != fields["css"]:
            # get_or_create: a second run must not replace the saved copy with the new CSS.
            StyleSheet.objects.get_or_create(
                name=backup_name(current.name),
                defaults={
                    "display_name": f"{current.display_name} (before the audit fixes)"[:200],
                    "description": (
                        f"The '{current.name}' sheet as it was before the production audit fixes. "
                        f"To switch back, activate this sheet and deactivate '{current.name}', "
                        "or copy this CSS into it."
                    ),
                    "css": current.css,
                    "is_active": False,
                    "sort_order": current.sort_order,
                },
            )
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


def restore_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    for name in SYNCED_SHEETS:
        backup = StyleSheet.objects.filter(name=backup_name(name)).first()
        if backup is None:
            continue
        sheet = StyleSheet.objects.filter(name=name).first()
        if sheet is None:
            # Keep the copy if its sheet has been deleted since, so the old CSS is not lost.
            continue
        sheet.css = backup.css
        # An admin who switched back by activating the copy keeps that CSS served.
        sheet.is_active = sheet.is_active or backup.is_active
        sheet.save(update_fields=["css", "is_active"])
        backup.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0021_ucm_subsite_redesign"),
    ]

    operations = [
        migrations.RunPython(update_design_tokens, restore_design_tokens),
        migrations.RunPython(sync_stylesheets, restore_stylesheets),
    ]
