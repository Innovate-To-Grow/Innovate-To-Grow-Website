"""
Add GrapesJS fields (html, css, grapesjs_json, dynamic_config) to Page and HomePage.

These fields were originally added here because 0001_initial was applied before
the GrapesJS mixin existed. The fields have since been folded into 0001_initial,
so this migration is now a no-op. It is kept to avoid breaking the migration graph
for databases that already applied it.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0001_initial"),
    ]

    operations = []
