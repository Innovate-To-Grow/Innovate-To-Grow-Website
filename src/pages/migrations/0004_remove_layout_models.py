# Migration to remove layout models from pages app state
# These models are now managed by the layout app

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0003_footercontent"),
        ("layout", "0001_initial"),  # Ensure layout has claimed these models first
    ]

    operations = [
        # Use SeparateDatabaseAndState to remove models from pages state
        # without deleting database tables (they belong to layout now)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="FooterContent"),
            ],
            database_operations=[],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
        migrations.AlterUniqueTogether(
            name="menupagelink",
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name="menupagelink",
            name="menu",
        ),
        migrations.RemoveField(
            model_name="menupagelink",
            name="page",
        ),
                migrations.DeleteModel(name="Menu"),
                migrations.DeleteModel(name="MenuPageLink"),
            ],
            database_operations=[],
        ),
    ]
