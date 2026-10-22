"""Stop serving the content stylesheets from the database.

The frontend bundle ships their rules in pages/src/styles/contract/, which every page loads, so
the last four seed sheets are switched off (not deleted) and their description says where the
CSS lives now. After this migration /layout/styles.css serves only the design tokens. A sheet an
admin had already switched off is left alone; the reverse switches back on only the sheets this
migration switched off.

Ship this in a release after the frontend that bundles pages/src/styles/contract/ is live in
production: the backend deploys first, so a release carrying both would leave every CMS page
unstyled until the frontend deploy finishes. Run ``python manage.py stylesheet_drift --diff`` before
deploying and port any admin edit worth keeping into the matching contract file.
"""

from django.db import migrations

RETIRED_PREFIX = "Retired: the frontend bundle ships this CSS"

# Sheet name -> where its rules live now (paths under pages/src).
RETIRED_SHEETS = {
    "global": "styles/contract/global/",
    "cms-blocks": "styles/contract/cms-blocks/",
    "cms-pages": "styles/contract/cms-pages.css",
    "page-home": "styles/contract/page-home.css",
}


def _note(path):
    return f"{RETIRED_PREFIX} (pages/src/{path}).\n"


def retire(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")
    for sheet in StyleSheet.objects.filter(name__in=RETIRED_SHEETS, is_active=True):
        sheet.is_active = False
        if not sheet.description.startswith(RETIRED_PREFIX):
            sheet.description = _note(RETIRED_SHEETS[sheet.name]) + sheet.description
        sheet.save(update_fields=["is_active", "description"])


def _without_note(description, path):
    """The description without this migration's note, or None when it does not start with it.

    A save from the admin's textarea stores the note's line break as CRLF, so any line ending counts.
    """
    head = _note(path).rstrip("\n")
    if not description.startswith(head):
        return None
    rest = description[len(head) :]
    if rest.startswith("\r\n"):
        return rest[2:]
    return rest[1:] if rest[:1] in ("\n", "\r") else rest


def restore(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")
    for sheet in StyleSheet.objects.filter(name__in=RETIRED_SHEETS, is_active=False):
        description = _without_note(sheet.description, RETIRED_SHEETS[sheet.name])
        if description is None:
            continue
        sheet.is_active = True
        sheet.description = description
        sheet.save(update_fields=["is_active", "description"])


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0026_retire_component_stylesheets"),
    ]

    operations = [
        migrations.RunPython(retire, restore),
    ]
