"""Remove google_sheet and schedule_grid CMS block types.

Soft-deletes any existing CMSBlock rows that use these block types
and updates the block_type field choices.
"""

from django.db import migrations, models
from django.utils import timezone


def soft_delete_sheet_blocks(apps, schema_editor):
    CMSBlock = apps.get_model("pages", "CMSBlock")
    CMSBlock.objects.filter(
        block_type__in=("google_sheet", "schedule_grid"),
        is_deleted=False,
    ).update(is_deleted=True, deleted_at=timezone.now())


def restore_sheet_blocks(apps, schema_editor):
    CMSBlock = apps.get_model("pages", "CMSBlock")
    CMSBlock.objects.filter(
        block_type__in=("google_sheet", "schedule_grid"),
        is_deleted=True,
    ).update(is_deleted=False, deleted_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0017_remove_googlesheetsource"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cmsblock",
            name="block_type",
            field=models.CharField(
                choices=[
                    ("hero", "Hero Banner"),
                    ("rich_text", "Rich Text"),
                    ("faq_list", "FAQ List"),
                    ("link_list", "Link List"),
                    ("cta_group", "CTA Buttons"),
                    ("image_text", "Image + Text"),
                    ("notice", "Notice / Callout"),
                    ("contact_info", "Contact Info"),
                    ("section_group", "Section Group"),
                    ("table", "Data Table"),
                    ("numbered_list", "Numbered List"),
                    ("proposal_cards", "Proposal Cards"),
                    ("navigation_grid", "Navigation Grid"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(soft_delete_sheet_blocks, restore_sheet_blocks),
    ]
