"""
Add GrapesJS fields (html, css, grapesjs_json, dynamic_config) to Page and HomePage.

These fields were defined in the GrapesJSPageMixin and included in 0001_initial,
but the migration was applied before the mixin existed, so the columns are missing
from the actual database tables.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0001_initial"),
    ]

    operations = [
        # Page fields
        migrations.AddField(
            model_name="page",
            name="html",
            field=models.TextField(blank=True, default="", help_text="Rendered HTML output from GrapesJS."),
        ),
        migrations.AddField(
            model_name="page",
            name="css",
            field=models.TextField(blank=True, default="", help_text="CSS output from GrapesJS."),
        ),
        migrations.AddField(
            model_name="page",
            name="grapesjs_json",
            field=models.JSONField(blank=True, default=dict, help_text="GrapesJS project data for editor loading."),
        ),
        migrations.AddField(
            model_name="page",
            name="dynamic_config",
            field=models.JSONField(blank=True, default=dict, help_text="Dynamic data source configuration for this page."),
        ),
        # HomePage fields
        migrations.AddField(
            model_name="homepage",
            name="html",
            field=models.TextField(blank=True, default="", help_text="Rendered HTML output from GrapesJS."),
        ),
        migrations.AddField(
            model_name="homepage",
            name="css",
            field=models.TextField(blank=True, default="", help_text="CSS output from GrapesJS."),
        ),
        migrations.AddField(
            model_name="homepage",
            name="grapesjs_json",
            field=models.JSONField(blank=True, default=dict, help_text="GrapesJS project data for editor loading."),
        ),
        migrations.AddField(
            model_name="homepage",
            name="dynamic_config",
            field=models.JSONField(blank=True, default=dict, help_text="Dynamic data source configuration for this page."),
        ),
    ]
