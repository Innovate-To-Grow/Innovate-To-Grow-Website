"""Remove CMSPage.page_css.

Page styles now live in the repository (pages/src) and site-wide overrides in Site Settings
(custom CSS), so a page no longer carries its own CSS. Dropping the column must not lose any: if a
page (published or draft) still has Page CSS, the migration stops before changing anything and
names the pages. Move the rules they still need into the repository, clear the field in the admin,
then deploy again. The reverse brings the column back empty.
"""

from django.db import migrations


def refuse_to_drop_page_css(apps, schema_editor):
    CMSPage = apps.get_model("cms", "CMSPage")
    pages = CMSPage.objects.exclude(page_css="").only("route", "status", "page_css").order_by("route")
    kept = [f"{page.route} ({page.status})" for page in pages if page.page_css.strip()]
    if kept:
        raise RuntimeError(
            "These CMS pages still have Page CSS, which this migration would delete: "
            f"{', '.join(kept)}. Move the rules they need into the repository, clear Page CSS in the "
            "admin, and run the migration again."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0030_delete_stylesheet"),
    ]

    operations = [
        migrations.RunPython(refuse_to_drop_page_css, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="cmspage",
            name="page_css",
        ),
    ]
