"""Move CMSPage and CMSBlock from cms app to pages app (state only).

Uses SeparateDatabaseAndState so no database tables are touched.
The existing cms_cmspage and cms_cmsblock tables are reused via db_table.
"""

import django.core.serializers.json
import django.db.models.deletion
import uuid
from django.db import migrations, models


def update_content_types(apps, schema_editor):
    """Update ContentType records from cms to pages."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="cms", model="cmspage").update(app_label="pages")
    ContentType.objects.filter(app_label="cms", model="cmsblock").update(app_label="pages")


def reverse_content_types(apps, schema_editor):
    """Reverse: update ContentType records from pages back to cms."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="pages", model="cmspage").update(app_label="cms")
    ContentType.objects.filter(app_label="pages", model="cmsblock").update(app_label="cms")


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0013_googlesheetsource_to_projectcontrolmodel"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="CMSPage",
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
                        ("is_deleted", models.BooleanField(db_index=True, default=False)),
                        ("deleted_at", models.DateTimeField(blank=True, null=True)),
                        ("version", models.PositiveIntegerField(default=0, editable=False)),
                        (
                            "slug",
                            models.SlugField(
                                help_text="Stable identifier for import/export. Do not change after publishing.",
                                max_length=200,
                                unique=True,
                            ),
                        ),
                        (
                            "route",
                            models.CharField(
                                help_text="Frontend route path, e.g. '/about'. Must start with '/'.",
                                max_length=200,
                                unique=True,
                            ),
                        ),
                        ("title", models.CharField(max_length=300)),
                        ("meta_description", models.TextField(blank=True, default="")),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("draft", "Draft"),
                                    ("published", "Published"),
                                    ("archived", "Archived"),
                                ],
                                db_index=True,
                                default="draft",
                                max_length=10,
                            ),
                        ),
                        ("published_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "page_css_class",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="CSS class for the page wrapper div, e.g. 'about-page'.",
                                max_length=100,
                            ),
                        ),
                        ("sort_order", models.IntegerField(default=0)),
                    ],
                    options={
                        "verbose_name": "CMS Page",
                        "verbose_name_plural": "CMS Pages",
                        "ordering": ["sort_order", "title"],
                        "db_table": "cms_cmspage",
                        "indexes": [
                            models.Index(
                                fields=["route", "status"],
                                name="cms_cmspage_route_08f33c_idx",
                            )
                        ],
                    },
                ),
                migrations.CreateModel(
                    name="CMSBlock",
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
                        ("is_deleted", models.BooleanField(db_index=True, default=False)),
                        ("deleted_at", models.DateTimeField(blank=True, null=True)),
                        ("version", models.PositiveIntegerField(default=0, editable=False)),
                        (
                            "block_type",
                            models.CharField(
                                choices=[
                                    ("hero", "Hero Banner"),
                                    ("rich_text", "Rich Text"),
                                    ("faq_list", "FAQ List"),
                                    ("link_list", "Link List"),
                                    ("cta_group", "CTA Buttons"),
                                    ("image_text", "Image + Text"),
                                    ("notice", "Notice / Callout"),
                                    ("contact_info", "Contact Info"),
                                    ("google_sheet", "Google Sheet Embed"),
                                    ("section_group", "Section Group"),
                                    ("table", "Data Table"),
                                    ("numbered_list", "Numbered List"),
                                    ("proposal_cards", "Proposal Cards"),
                                    ("navigation_grid", "Navigation Grid"),
                                    ("schedule_grid", "Schedule Grid"),
                                ],
                                max_length=30,
                            ),
                        ),
                        ("sort_order", models.IntegerField(default=0)),
                        (
                            "data",
                            models.JSONField(
                                default=dict,
                                encoder=django.core.serializers.json.DjangoJSONEncoder,
                            ),
                        ),
                        (
                            "admin_label",
                            models.CharField(
                                blank=True,
                                default="",
                                help_text="Label shown in admin for easier identification.",
                                max_length=200,
                            ),
                        ),
                        (
                            "page",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="blocks",
                                to="pages.cmspage",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Content Block",
                        "verbose_name_plural": "Content Blocks",
                        "ordering": ["sort_order"],
                        "db_table": "cms_cmsblock",
                        "indexes": [
                            models.Index(
                                fields=["page", "sort_order"],
                                name="cms_cmsbloc_page_id_455329_idx",
                            )
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(
            update_content_types,
            reverse_content_types,
        ),
    ]
