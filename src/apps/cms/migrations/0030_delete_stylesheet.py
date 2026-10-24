"""Delete the StyleSheet table.

0026 and 0027 switched every row off: the frontend bundle ships all of the site's CSS. The rows go
with the table, so before deploying this, keep a copy with the previous release's command:
``python manage.py stylesheet_drift --export stylesheets-backup.json``. The reverse creates an empty
table; restore rows from that file if they are ever needed. migrations/data/stylesheets.json stays:
the earlier migrations read it.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0029_customcssrevision"),
    ]

    operations = [
        migrations.DeleteModel(
            name="StyleSheet",
        ),
    ]
