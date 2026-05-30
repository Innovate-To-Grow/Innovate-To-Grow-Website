from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


def migrate_hide_section_titles(apps, schema_editor):
    CMSEmbedWidget = apps.get_model("cms", "CMSEmbedWidget")
    CMSEmbedWidget.objects.filter(hide_section_titles=True).update(hidden_sections=["section_titles"])


def reverse_migrate_hide_section_titles(apps, schema_editor):
    CMSEmbedWidget = apps.get_model("cms", "CMSEmbedWidget")
    for widget in CMSEmbedWidget.objects.all().only("pk", "hidden_sections"):
        hidden_sections = widget.hidden_sections if isinstance(widget.hidden_sections, list) else []
        CMSEmbedWidget.objects.filter(pk=widget.pk).update(
            hide_section_titles="section_titles" in hidden_sections,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0011_cmsembedwidget_hide_section_titles_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="cmsembedwidget",
            name="hidden_sections",
            field=models.JSONField(
                blank=True,
                default=list,
                encoder=DjangoJSONEncoder,
                help_text="List of safe section preset keys to hide inside the embed iframe.",
            ),
        ),
        migrations.RunPython(migrate_hide_section_titles, reverse_migrate_hide_section_titles),
    ]
