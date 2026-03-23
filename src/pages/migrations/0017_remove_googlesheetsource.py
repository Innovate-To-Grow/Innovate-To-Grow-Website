"""Remove GoogleSheetSource from pages app state (moved to sheets app)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0016_sitesettings_homepage_page"),
        ("sheets", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="GoogleSheetSource"),
            ],
            database_operations=[],
        ),
    ]
