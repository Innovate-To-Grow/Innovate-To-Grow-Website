"""Let running text span the content column again.

0022 capped CMS prose, news stories and app copy at the layout.prose_max_width design token
(75ch), so on a desktop a paragraph stopped near the middle of the 1170px column while its
heading ran the full width. The token's default is now "none". This moves a Site Settings
row still holding the 75ch that 0022 added to "none"; a value an admin chose is kept. The
reverse puts 75ch back where the token is still "none".
"""

from django.db import migrations

GROUP = "layout"
KEY = "prose_max_width"
CAPPED = "75ch"
FULL_WIDTH = "none"


def _replace_token(apps, old, new):
    SiteSettings = apps.get_model("cms", "SiteSettings")
    for settings in SiteSettings.objects.all():
        tokens = settings.design_tokens
        group = tokens.get(GROUP) if isinstance(tokens, dict) else None
        if not isinstance(group, dict) or group.get(KEY) != old:
            continue
        group[KEY] = new
        settings.save(update_fields=["design_tokens"])


def full_width(apps, schema_editor):
    _replace_token(apps, CAPPED, FULL_WIDTH)


def capped(apps, schema_editor):
    _replace_token(apps, FULL_WIDTH, CAPPED)


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0031_remove_cmspage_page_css"),
    ]

    operations = [
        migrations.RunPython(full_width, capped),
    ]
