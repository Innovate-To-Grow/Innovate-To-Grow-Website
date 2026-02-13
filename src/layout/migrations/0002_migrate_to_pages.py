# Migrate layout models to pages app (state-only, no database changes).
# The database tables already use the 'pages_' prefix, so no schema changes needed.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("layout", "0001_initial"),
    ]

    operations = [
        # State-only operations: remove models from layout app's Django state.
        # The actual database tables remain untouched.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="menupagelink",
                    name="menu",
                ),
                migrations.RemoveField(
                    model_name="menupagelink",
                    name="page",
                ),
                migrations.RemoveField(
                    model_name="menu",
                    name="pages",
                ),
                migrations.DeleteModel(
                    name="MenuPageLink",
                ),
                migrations.DeleteModel(
                    name="Menu",
                ),
                migrations.DeleteModel(
                    name="FooterContent",
                ),
            ],
            database_operations=[],
        ),
    ]
