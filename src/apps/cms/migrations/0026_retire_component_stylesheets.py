"""Stop serving the component stylesheets from the database.

Their rules ship with the frontend bundle, in CSS files next to the React components that
render them, so the rows are switched off (not deleted) and their description says where the
CSS lives now. A sheet an admin had already switched off is left alone. The reverse switches
back on only the sheets this migration switched off.

Ship this in a release after the frontend that bundles these rules is live in production: the
backend deploys first, so a release carrying both would leave the live frontend without them until
its own deploy finishes. Run ``python manage.py stylesheet_drift --diff`` before deploying: an admin
edit to one of these rows stops showing once the row is off, so port any edit worth keeping into the
frontend file.
"""

from django.db import migrations

RETIRED_PREFIX = "Retired: the frontend bundle ships this CSS"

# Sheet name -> where its rules live now (paths under pages/src).
RETIRED_SHEETS = {
    "layout-container": "features/layout/components/Container/Container.css",
    "layout-menu": "features/layout/components/MainMenu/MainMenu.css",
    "layout-footer": "features/layout/components/Footer/Footer.css",
    "auth": "features/auth/components/auth.css, forms/CodeInput.css and styles/orgToggle.css",
    "page-news": "routes/NewsPage/ and routes/NewsDetailPage/",
    "page-projects": "features/projects/components/projects.css",
    "page-events": (
        "routes/EventRegistrationPage/, routes/SchedulePage/, features/events/ "
        "and styles/contract/legacy-content.css"
    ),
    "page-subscribe": "routes/SubscribePage/SubscribePage.css",
    "page-misc": (
        "components/NotFoundPage/, app/ErrorBoundary/ and features/auth/components/shared/linkLandingPages.css"
    ),
    "maintenance": "app/MaintenanceMode/MaintenanceMode.css",
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
        ("cms", "0025_menu_dropdown_fit_content"),
    ]

    operations = [
        migrations.RunPython(retire, restore),
    ]
