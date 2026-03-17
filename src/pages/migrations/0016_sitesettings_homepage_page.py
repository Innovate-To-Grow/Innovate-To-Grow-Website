from django.db import migrations, models


def _normalize_route(route):
    route = (route or "").strip()
    if not route:
        return "/"

    segments = [segment.strip() for segment in route.split("/") if segment.strip()]
    if not segments:
        return "/"

    return "/" + "/".join(segments)


def backfill_homepage_page(apps, schema_editor):
    SiteSettings = apps.get_model("pages", "SiteSettings")
    CMSPage = apps.get_model("pages", "CMSPage")

    for settings in SiteSettings.objects.all():
        route = _normalize_route(getattr(settings, "homepage_route", "/"))
        homepage_page = CMSPage.objects.filter(route=route, status="published", is_deleted=False).first()

        if homepage_page is None:
            homepage_page = CMSPage.objects.filter(route="/", status="published", is_deleted=False).first()

        settings.homepage_page_id = getattr(homepage_page, "pk", None)
        settings.save(update_fields=["homepage_page"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0015_ensure_cms_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="homepage_page",
            field=models.ForeignKey(
                blank=True,
                help_text='Published CMS page to render at "/". Leave blank to use the published "/" page.',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="+",
                to="pages.cmspage",
            ),
        ),
        migrations.RunPython(backfill_homepage_page, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="sitesettings",
            name="homepage_mode",
        ),
        migrations.RemoveField(
            model_name="sitesettings",
            name="homepage_route",
        ),
    ]
