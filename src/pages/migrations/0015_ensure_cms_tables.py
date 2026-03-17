"""Ensure cms_cmspage and cms_cmsblock tables exist.

On databases migrated from the old cms app, the tables already exist.
On fresh databases (where the cms app was never installed), this
migration creates them so the pages app's CMSPage/CMSBlock models work.

Also cleans up orphaned cms migration records from django_migrations.
"""

from django.db import migrations


def create_cms_tables_if_missing(apps, schema_editor):
    """Create cms_cmspage and cms_cmsblock if they don't exist yet."""
    connection = schema_editor.connection
    existing_tables = connection.introspection.table_names()

    if "cms_cmspage" not in existing_tables:
        CMSPage = apps.get_model("pages", "CMSPage")
        schema_editor.create_model(CMSPage)

    if "cms_cmsblock" not in existing_tables:
        CMSBlock = apps.get_model("pages", "CMSBlock")
        schema_editor.create_model(CMSBlock)


def cleanup_cms_migration_records(apps, schema_editor):
    """Remove orphaned cms migration records from django_migrations."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM django_migrations WHERE app = 'cms'")


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0014_adopt_cms_models"),
    ]

    operations = [
        migrations.RunPython(
            create_cms_tables_if_missing,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            cleanup_cms_migration_records,
            migrations.RunPython.noop,
        ),
    ]
