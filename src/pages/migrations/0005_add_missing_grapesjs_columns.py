"""
Fix missing GrapesJS columns on production databases.

Migration 0002_add_grapesjs_fields was turned into a no-op after its AddField
operations were folded into 0001_initial. However, production databases that
already applied the original 0001 (without GrapesJS fields) never received
those columns.

This migration checks whether columns exist before adding them, so it is safe
for both production (columns missing) and fresh installs (columns already exist).
"""

from django.db import connection, migrations

# Columns to add: (table_name, column_name, sql_type, default_value)
COLUMNS_TO_ADD = [
    ("pages_page", "html", "text", "''"),
    ("pages_page", "css", "text", "''"),
    ("pages_page", "grapesjs_json", "jsonb", "'{}'"),
    ("pages_page", "dynamic_config", "jsonb", "'{}'"),
    ("pages_homepage", "html", "text", "''"),
    ("pages_homepage", "css", "text", "''"),
    ("pages_homepage", "grapesjs_json", "jsonb", "'{}'"),
    ("pages_homepage", "dynamic_config", "jsonb", "'{}'"),
]


def add_missing_columns(apps, schema_editor):
    """Add GrapesJS columns if they don't already exist."""
    db_engine = connection.vendor

    for table, column, col_type, default in COLUMNS_TO_ADD:
        if db_engine == "postgresql":
            schema_editor.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                f"{column} {col_type} DEFAULT {default} NOT NULL;"
            )
        else:
            # SQLite: check if column exists via PRAGMA
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA table_info({table})")
                existing_columns = [row[1] for row in cursor.fetchall()]
                if column not in existing_columns:
                    # SQLite uses 'text' for both text and json
                    sqlite_type = "text" if col_type == "jsonb" else col_type
                    sqlite_default = "'{}'" if col_type == "jsonb" else default
                    schema_editor.execute(
                        f"ALTER TABLE {table} ADD COLUMN "
                        f"{column} {sqlite_type} DEFAULT {sqlite_default} NOT NULL;"
                    )


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0004_homepage_scheduled_publish_at_and_more"),
    ]

    operations = [
        migrations.RunPython(
            add_missing_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
