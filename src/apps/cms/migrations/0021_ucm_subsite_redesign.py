"""Restyle the site as a UC Merced School of Engineering subsite.

1. Moves SiteSettings.design_tokens to the new defaults. A token is replaced only
   while it still holds the previous default, so values an admin changed are kept;
   tokens the previous defaults did not have are added.
2. Re-syncs every StyleSheet from data/stylesheets.json, which now carries the
   redesigned header, footer, page and block styles. The CSS stays CMS-managed:
   before a sheet's CSS is replaced, it is kept as an inactive
   "<name>-pre-redesign" sheet, so an admin can compare it or switch back.

The reverse copies those saved sheets back and returns tokens that still hold
the new defaults to the previous ones.
"""

import json
from pathlib import Path

from django.db import migrations

PREVIOUS_DEFAULT_TOKENS = {
    "colors": {
        "primary": "#0f2d52",
        "primary_hover": "#1a4a7a",
        "text": "#444",
        "text_dark": "#333",
        "text_secondary": "#666",
        "bg_light": "#f8f9fa",
        "bg_page": "#f9f9f9",
        "white": "#fff",
        "border": "#e0e0e0",
        "border_table": "#ccc",
        "accent_gold": "#daa520",
        "accent_gold_hover": "#c4941a",
        "accent_bright": "#FFBF3C",
        "error": "#c00",
        "error_light": "#b30000",
    },
    "typography": {
        "font_size_hero": "2.5rem",
        "font_size_h1": "2rem",
        "font_size_h2": "1.5rem",
        "font_size_h3": "1.25rem",
        "font_size_h4": "1.1rem",
        "font_size_lead": "1.1875rem",
        "font_size_subtitle": "1.125rem",
        "font_size_body": "1rem",
        "font_size_meta": "0.9375rem",
        "font_size_small": "0.875rem",
        "font_size_label": "0.8125rem",
        "line_height_body": "1.7",
        "line_height_meta": "1.6",
        "line_height_heading": "1.3",
        "line_height_card": "1.4",
        "line_height_summary": "1.5",
    },
    "typography_mobile": {
        "font_size_hero_mobile": "1.75rem",
        "font_size_h1_mobile": "1.5rem",
        "font_size_h2_mobile": "1.25rem",
        "font_size_h3_mobile": "1.125rem",
        "font_size_h4_mobile": "1rem",
        "font_size_lead_mobile": "1.0625rem",
        "font_size_table_mobile": "0.875rem",
    },
    "layout": {
        "page_max_width": "1200px",
        "page_narrow_width": "900px",
        "page_padding": "2rem 1rem",
        "page_padding_mobile": "1rem",
        "section_gap": "2rem",
        "list_indent": "1.5rem",
    },
    "borders": {
        "radius_card": "8px",
        "radius_button": "4px",
        "radius_image": "8px",
    },
    "effects": {
        "transition_fast": "0.2s",
        "transition_link": "0.15s",
        "shadow_card_hover": "0 4px 16px rgba(0, 0, 0, 0.12)",
    },
}

NEW_DEFAULT_TOKENS = {
    "colors": {
        "primary": "#0f2d52",
        "primary_hover": "#005487",
        "secondary": "#005487",
        "text": "#323336",
        "text_dark": "#333333",
        "text_secondary": "#555555",
        "bg_light": "#f2f2f2",
        "bg_panel": "#f7f7f7",
        "bg_page": "#ffffff",
        "white": "#fff",
        "border": "#dddddd",
        "border_table": "#cccccc",
        "border_input": "#cccccc",
        "accent_gold": "#dbaa00",
        "accent_gold_hover": "#be882c",
        "accent_bright": "#ffbf3c",
        "accent_menu": "#f8bd38",
        "sidebar_rule": "#0f5479",
        "footer_bar": "#142d52",
        "footer_bar_rule": "#d9a928",
        "highlight": "#fff6db",
        "tag_new": "#ffe9a8",
        "success": "#1e7b34",
        "disabled_text": "#6b6b6b",
        "disabled_bg": "#efefef",
        "disabled_border": "#d6d6d6",
        "footer_bg": "#e5e5e5",
        "error": "#9b1c1c",
        "error_light": "#b30000",
    },
    "typography": {
        "font_family_body": "'Open Sans', 'Segoe UI', Arial, sans-serif",
        "font_family_display": "'Khula', 'Open Sans', 'Segoe UI', Arial, sans-serif",
        "font_size_hero": "3rem",
        "font_size_h1": "2.25rem",
        "font_size_h2": "1.75rem",
        "font_size_h3": "1.5rem",
        "font_size_h4": "1.25rem",
        "font_size_lead": "1.125rem",
        "font_size_subtitle": "1.125rem",
        "font_size_body": "1rem",
        "font_size_meta": "1rem",
        "font_size_small": "0.875rem",
        "font_size_label": "1rem",
        "line_height_body": "1.5",
        "line_height_meta": "1.5",
        "line_height_heading": "1.5",
        "line_height_card": "1.4",
        "line_height_summary": "1.5",
    },
    "typography_mobile": {
        "font_size_hero_mobile": "2rem",
        "font_size_h1_mobile": "2.25rem",
        "font_size_h2_mobile": "1.75rem",
        "font_size_h3_mobile": "1.5rem",
        "font_size_h4_mobile": "1.25rem",
        "font_size_lead_mobile": "1.125rem",
        "font_size_table_mobile": "0.875rem",
    },
    "layout": {
        "page_max_width": "1170px",
        "page_narrow_width": "870px",
        "page_gutter": "1.5rem",
        "page_gutter_mobile": "1.25rem",
        "page_padding": "1rem 1.5rem 3rem",
        "page_padding_mobile": "1rem 1.25rem 2.5rem",
        "sidebar_width": "270px",
        "section_gap": "2rem",
        "list_indent": "1.5625rem",
    },
    "borders": {
        "radius_card": "0",
        "radius_button": "0",
        "radius_image": "0",
        "radius_input": "4px",
    },
    "effects": {
        "transition_fast": "0.2s",
        "transition_link": "0.15s",
        "shadow_card_hover": "0 2px 8px rgba(15, 45, 82, 0.12)",
        "shadow_header": "0 6px 6px -2px rgba(121, 121, 121, 0.67)",
    },
}


BACKUP_SUFFIX = "-pre-redesign"


def backup_name(name):
    return f"{name}{BACKUP_SUFFIX}"


def merge_tokens(current):
    tokens = {group: dict(values) for group, values in (current or {}).items() if isinstance(values, dict)}
    for group, values in NEW_DEFAULT_TOKENS.items():
        target = tokens.setdefault(group, {})
        previous = PREVIOUS_DEFAULT_TOKENS.get(group, {})
        for key, value in values.items():
            if key not in target or target[key] == previous.get(key):
                target[key] = value
    return tokens


def unmerge_tokens(current):
    """Undo merge_tokens for every token that still holds the new default."""
    tokens = {group: dict(values) for group, values in (current or {}).items() if isinstance(values, dict)}
    for group, values in NEW_DEFAULT_TOKENS.items():
        target = tokens.get(group)
        if target is None:
            continue
        previous = PREVIOUS_DEFAULT_TOKENS.get(group, {})
        for key, value in values.items():
            if target.get(key) != value:
                continue
            if key in previous:
                target[key] = previous[key]
            else:
                del target[key]
        if not target and group not in PREVIOUS_DEFAULT_TOKENS:
            del tokens[group]
    return tokens


def update_design_tokens(apps, schema_editor):
    SiteSettings = apps.get_model("cms", "SiteSettings")
    for settings in SiteSettings.objects.all():
        settings.design_tokens = merge_tokens(settings.design_tokens)
        settings.save(update_fields=["design_tokens"])


def restore_design_tokens(apps, schema_editor):
    SiteSettings = apps.get_model("cms", "SiteSettings")
    for settings in SiteSettings.objects.all():
        settings.design_tokens = unmerge_tokens(settings.design_tokens)
        settings.save(update_fields=["design_tokens"])


def load_seed_sheets():
    data_path = Path(__file__).resolve().parent / "data" / "stylesheets.json"
    if not data_path.exists():
        return []
    with open(data_path) as f:
        return [record["fields"] for record in json.load(f)]


def sync_stylesheets(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")

    for fields in load_seed_sheets():
        current = StyleSheet.objects.filter(name=fields["name"]).first()
        if current is not None and current.css != fields["css"]:
            # get_or_create: a second run must not replace the saved copy with the new CSS.
            StyleSheet.objects.get_or_create(
                name=backup_name(current.name),
                defaults={
                    "display_name": f"{current.display_name} (before the redesign)"[:200],
                    "description": (
                        f"The '{current.name}' sheet as it was before the UC Merced subsite redesign. "
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

    for fields in load_seed_sheets():
        backup = StyleSheet.objects.filter(name=backup_name(fields["name"])).first()
        if backup is None:
            continue
        sheet = StyleSheet.objects.filter(name=fields["name"]).first()
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
        ("cms", "0020_pageview_visitor_id"),
    ]

    operations = [
        migrations.RunPython(update_design_tokens, restore_design_tokens),
        migrations.RunPython(sync_stylesheets, restore_stylesheets),
    ]
