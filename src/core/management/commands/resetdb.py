"""
Django Management Command: resetdb

Resets the database and migration files, then recreates everything from scratch.

Usage:
    python manage.py resetdb --force --confirm RESET_DB
    python manage.py resetdb --force --confirm RESET_DB --keep-migrations
"""

import os
import shutil

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections


class Command(BaseCommand):
    help = "Resets database and migration files, then recreates everything (DEV ONLY)."

    # Default admin credentials
    DEV_DEFAULT_ADMIN_USERNAME = "hongzhe"
    DEV_DEFAULT_ADMIN_EMAIL = "xiehongzhe04@gmail.com"
    DEV_DEFAULT_ADMIN_PASSWORD = "1"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required flag to acknowledge the destructive nature of this command.",
        )
        parser.add_argument(
            "--confirm",
            type=str,
            help='Required confirmation string. Must be "RESET_DB".',
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help=f'The database to reset. Defaults to "{DEFAULT_DB_ALIAS}".',
        )
        parser.add_argument(
            "--keep-migrations",
            action="store_true",
            help="Keep existing migration files (only reset database).",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Allow running even if DEBUG is False (dangerous).",
        )

    def handle(self, *args, **options):
        db_alias = options["database"]
        force = options["force"]
        confirm = options["confirm"]
        allow_production = options["allow_production"]
        keep_migrations = options["keep_migrations"]

        # Guardrails
        if not settings.DEBUG and not allow_production:
            raise CommandError("Command restricted to DEBUG=True. Use --allow-production to override.")

        if not force or confirm != "RESET_DB":
            raise CommandError("Destructive command requires --force and --confirm RESET_DB.")

        if not settings.DEBUG and allow_production:
            self.stdout.write(self.style.WARNING("*** WARNING: RUNNING RESETDB IN PRODUCTION ENVIRONMENT ***"))

        connection = connections[db_alias]
        db_settings = connection.settings_dict
        vendor = connection.vendor

        self.stdout.write(self.style.NOTICE("=" * 60))
        self.stdout.write(self.style.NOTICE("DATABASE RESET"))
        self.stdout.write(self.style.NOTICE("=" * 60))
        self.stdout.write(f"  Vendor: {vendor}")
        self.stdout.write(f"  Database: {db_settings.get('NAME')}")
        self.stdout.write("")

        # Step 1: Delete migration files (unless --keep-migrations)
        if not keep_migrations:
            self._delete_migration_files()

        # Step 2: Reset database
        self.stdout.write(self.style.NOTICE("Resetting database..."))
        try:
            if vendor == "postgresql":
                self._reset_postgresql(connection)
            elif vendor == "mysql":
                self._reset_mysql(connection)
            elif vendor == "sqlite":
                self._reset_sqlite(connection)
            else:
                raise CommandError(f"Unsupported database vendor: {vendor}")
        except Exception as e:
            raise CommandError(f"Error during database reset: {e}")

        self.stdout.write(self.style.SUCCESS("Database cleared."))

        # Step 3: Make migrations
        self.stdout.write(self.style.NOTICE("Creating migrations..."))
        call_command("makemigrations", interactive=False)
        self.stdout.write(self.style.SUCCESS("Migrations created."))

        # Step 4: Apply migrations
        self.stdout.write(self.style.NOTICE("Applying migrations..."))
        call_command("migrate", database=db_alias, interactive=False)
        self.stdout.write(self.style.SUCCESS("Migrations applied."))

        # Step 5: Create default admin user
        self._create_default_admin()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("DATABASE RESET COMPLETE"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

    def _delete_migration_files(self):
        """Delete all migration files from all installed apps."""
        self.stdout.write(self.style.NOTICE("Deleting migration files..."))

        # Get the project's src directory
        base_dir = settings.BASE_DIR

        deleted_count = 0
        for app_config in apps.get_app_configs():
            # Only process apps within our project (not third-party)
            app_path = app_config.path
            if not app_path.startswith(str(base_dir)):
                continue

            migrations_dir = os.path.join(app_path, "migrations")
            if not os.path.exists(migrations_dir):
                continue

            # Delete all migration files except __init__.py
            for filename in os.listdir(migrations_dir):
                if filename == "__init__.py" or filename == "__pycache__":
                    continue

                file_path = os.path.join(migrations_dir, filename)
                if os.path.isfile(file_path) and filename.endswith(".py"):
                    os.remove(file_path)
                    self.stdout.write(f"  Deleted: {app_config.label}/migrations/{filename}")
                    deleted_count += 1
                elif os.path.isdir(file_path) and filename == "__pycache__":
                    shutil.rmtree(file_path)

            # Also clean __pycache__ in migrations folder
            pycache_dir = os.path.join(migrations_dir, "__pycache__")
            if os.path.exists(pycache_dir):
                shutil.rmtree(pycache_dir)

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} migration file(s)."))

    def _reset_postgresql(self, connection):
        """PostgreSQL reset: Drop public schema and recreate it."""
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")
            cursor.execute("GRANT ALL ON SCHEMA public TO public;")
            db_user = connection.settings_dict.get("USER")
            if db_user:
                cursor.execute(f"GRANT ALL ON SCHEMA public TO {db_user};")

    def _reset_mysql(self, connection):
        """MySQL reset: Disable FK checks and drop all tables."""
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("SHOW TABLES;")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS `{table}` CASCADE;")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    def _reset_sqlite(self, connection):
        """SQLite reset: Delete the database file."""
        db_name = connection.settings_dict["NAME"]

        if db_name == ":memory:":
            self.stdout.write("  Memory database detected.")
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
                for table in tables:
                    cursor.execute(f'DROP TABLE IF EXISTS "{table}";')
                cursor.execute("PRAGMA foreign_keys = ON;")
            return

        if os.path.exists(db_name):
            connection.close()
            try:
                os.remove(db_name)
                self.stdout.write(f"  Deleted SQLite file: {db_name}")
            except OSError as e:
                self.stdout.write(self.style.WARNING(f"  Could not delete SQLite file: {e}"))
                self._drop_sqlite_tables(connection)
        else:
            self.stdout.write(f"  SQLite file not found at {db_name}, nothing to delete.")

    def _drop_sqlite_tables(self, connection):
        """Fallback: drop all tables in SQLite."""
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
            for table in tables:
                cursor.execute(f'DROP TABLE IF EXISTS "{table}";')
            cursor.execute("PRAGMA foreign_keys = ON;")

    def _create_default_admin(self):
        """Create the default admin superuser."""
        self.stdout.write(self.style.NOTICE("Creating default admin user..."))

        # Import the Member model (custom user model)
        from authn.models import Member

        # Check if admin already exists
        if Member.objects.filter(username=self.DEV_DEFAULT_ADMIN_USERNAME).exists():
            self.stdout.write(f"  Admin user '{self.DEV_DEFAULT_ADMIN_USERNAME}' already exists.")
            return

        # Create superuser
        Member.objects.create_superuser(
            username=self.DEV_DEFAULT_ADMIN_USERNAME,
            email=self.DEV_DEFAULT_ADMIN_EMAIL,
            password=self.DEV_DEFAULT_ADMIN_PASSWORD,
        )

        self.stdout.write(self.style.SUCCESS("  Created admin user:"))
        self.stdout.write(f"    Username: {self.DEV_DEFAULT_ADMIN_USERNAME}")
        self.stdout.write(f"    Email:    {self.DEV_DEFAULT_ADMIN_EMAIL}")
        self.stdout.write(f"    Password: {self.DEV_DEFAULT_ADMIN_PASSWORD}")
