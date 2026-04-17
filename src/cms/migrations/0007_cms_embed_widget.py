# Generated manually for the CMSEmbedWidget extraction.

import uuid

import django.core.serializers.json
import django.db.models.deletion
from django.db import migrations, models


def copy_configs_to_widgets(apps, schema_editor):
    """Normalize CMSPage.embed_configs JSON entries into CMSEmbedWidget rows."""
    CMSPage = apps.get_model("cms", "CMSPage")
    CMSEmbedWidget = apps.get_model("cms", "CMSEmbedWidget")

    seen_slugs: set = set()
    for page in CMSPage.objects.all().only("id", "embed_configs"):
        for entry in page.embed_configs or []:
            if not isinstance(entry, dict):
                continue
            slug = str(entry.get("slug") or "").strip().lower()
            if not slug or slug in seen_slugs:
                continue
            refs_raw = entry.get("block_sort_orders") or []
            refs: list[int] = []
            for ref in refs_raw:
                try:
                    refs.append(int(ref))
                except (TypeError, ValueError):
                    continue
            CMSEmbedWidget.objects.create(
                page_id=page.id,
                slug=slug,
                admin_label=str(entry.get("admin_label") or "").strip()[:200],
                block_sort_orders=sorted(set(refs)),
            )
            seen_slugs.add(slug)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0006_cms_embed_configs"),
    ]

    operations = [
        migrations.CreateModel(
            name="CMSEmbedWidget",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "slug",
                    models.SlugField(
                        help_text="Globally unique kebab-case identifier used in the embed URL.",
                        max_length=120,
                        unique=True,
                    ),
                ),
                ("admin_label", models.CharField(blank=True, default="", max_length=200)),
                (
                    "block_sort_orders",
                    models.JSONField(
                        blank=True,
                        default=list,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                        help_text="List of CMSBlock.sort_order values to include, in declared order.",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="embed_widgets",
                        to="cms.cmspage",
                    ),
                ),
            ],
            options={
                "verbose_name": "CMS Embed Widget",
                "verbose_name_plural": "CMS Embed Widgets",
                "db_table": "cms_cmsembedwidget",
                "ordering": ["page__title", "slug"],
                "indexes": [models.Index(fields=["slug"], name="cms_cmsembe_slug_23e709_idx")],
            },
        ),
        migrations.RunPython(copy_configs_to_widgets, noop_reverse),
        migrations.RemoveField(
            model_name="cmspage",
            name="embed_configs",
        ),
    ]
