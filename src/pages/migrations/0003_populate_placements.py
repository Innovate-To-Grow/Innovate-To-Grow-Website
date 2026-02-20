"""
Step 2: Data migration - copy page/home_page/order from PageComponent
to PageComponentPlacement rows.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    PageComponent = apps.get_model("pages", "PageComponent")
    PageComponentPlacement = apps.get_model("pages", "PageComponentPlacement")

    placements = []
    for comp in PageComponent.objects.all():
        if comp.page_id:
            placements.append(
                PageComponentPlacement(
                    component=comp,
                    page_id=comp.page_id,
                    order=comp.order,
                )
            )
        if comp.home_page_id:
            placements.append(
                PageComponentPlacement(
                    component=comp,
                    home_page_id=comp.home_page_id,
                    order=comp.order,
                )
            )
    if placements:
        PageComponentPlacement.objects.bulk_create(placements)


def backwards(apps, schema_editor):
    PageComponentPlacement = apps.get_model("pages", "PageComponentPlacement")
    PageComponent = apps.get_model("pages", "PageComponent")

    for placement in PageComponentPlacement.objects.all():
        update_kwargs = {"order": placement.order}
        if placement.page_id:
            update_kwargs["page_id"] = placement.page_id
        if placement.home_page_id:
            update_kwargs["home_page_id"] = placement.home_page_id
        PageComponent.objects.filter(pk=placement.component_id).update(**update_kwargs)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0002_add_placement_through_table"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
