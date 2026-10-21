"""Size the desktop menu dropdowns to their links.

The "layout-menu" sheet gave every dropdown a fixed 362px panel (288px for the third level),
so a menu with short labels showed a wide, mostly empty box. The panels now take their
content's width: at least as wide as their menu item, at most the old fixed width (a longer
label wraps). Only the untouched declarations are rewritten, so an admin's own width edits
are kept; data/stylesheets.json carries the same rules for new databases. The reverse puts
the fixed widths back.
"""

from django.db import migrations

SHEET = "layout-menu"

REPLACEMENTS = [
    (
        "  z-index: 1100;\n  box-sizing: border-box;\n  width: 362px;\n",
        "  z-index: 1100;\n  box-sizing: border-box;\n  width: max-content;\n  min-width: 100%;\n  max-width: 362px;\n",
    ),
    (
        "  z-index: 1101;\n  box-sizing: border-box;\n  width: 288px;\n",
        "  z-index: 1101;\n  box-sizing: border-box;\n  width: max-content;\n  max-width: 288px;\n",
    ),
]


def _rewrite(apps, pairs):
    StyleSheet = apps.get_model("cms", "StyleSheet")
    sheet = StyleSheet.objects.filter(name=SHEET).first()
    if sheet is None:
        return
    css = sheet.css
    for old, new in pairs:
        if css.count(old) == 1:
            css = css.replace(old, new)
    if css != sheet.css:
        sheet.css = css
        sheet.save(update_fields=["css"])


def fit_content(apps, schema_editor):
    _rewrite(apps, REPLACEMENTS)


def fixed_width(apps, schema_editor):
    _rewrite(apps, [(new, old) for old, new in REPLACEMENTS])


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0024_member_button_label_style"),
    ]

    operations = [
        migrations.RunPython(fit_content, fixed_width),
    ]
