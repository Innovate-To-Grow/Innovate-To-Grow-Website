from django.db import migrations


def migrate_embed_widget_hidden_sections(apps, schema_editor):
    CMSBlock = apps.get_model("cms", "CMSBlock")
    for block in CMSBlock.objects.filter(block_type="embed_widget").only("pk", "data").iterator():
        data = block.data if isinstance(block.data, dict) else {}
        if data.get("hide_section_titles") is not True or "hidden_sections" in data:
            continue
        next_data = {**data, "hidden_sections": ["section_titles"]}
        CMSBlock.objects.filter(pk=block.pk).update(data=next_data)


def reverse_migrate_embed_widget_hidden_sections(apps, schema_editor):
    CMSBlock = apps.get_model("cms", "CMSBlock")
    for block in CMSBlock.objects.filter(block_type="embed_widget").only("pk", "data").iterator():
        data = block.data if isinstance(block.data, dict) else {}
        hidden_sections = data.get("hidden_sections")
        if not isinstance(hidden_sections, list):
            continue
        next_data = {**data, "hide_section_titles": "section_titles" in hidden_sections}
        if hidden_sections == ["section_titles"]:
            next_data.pop("hidden_sections", None)
        CMSBlock.objects.filter(pk=block.pk).update(data=next_data)


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0012_cmsembedwidget_hidden_sections"),
    ]

    operations = [
        migrations.RunPython(migrate_embed_widget_hidden_sections, reverse_migrate_embed_widget_hidden_sections),
    ]
