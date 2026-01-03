"""
Django Management Command: resetdb

Usage:
    python manage.py resetdb --force --confirm RESET_DB
    python manage.py resetdb --force --confirm RESET_DB --seed
    python manage.py resetdb --database reporting --force --confirm RESET_DB
"""

import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections


class Command(BaseCommand):
    help = "Drops all tables/schema and recreates the database via migrations (DEV/CI ONLY)."

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
            "--seed",
            action="store_true",
            help="Run data seeding after migration.",
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
        seed = options["seed"]

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

        self.stdout.write(f"Target Database: {db_alias}")
        self.stdout.write(f"  Vendor: {vendor}")
        self.stdout.write(f"  Database Name: {db_settings.get('NAME')}")
        self.stdout.write(f"  Host: {db_settings.get('HOST') or 'localhost'}")
        self.stdout.write(f"  User: {db_settings.get('USER')}")
        self.stdout.write("")

        self.stdout.write(self.style.NOTICE(f"Resetting database '{db_alias}'..."))

        try:
            if vendor == "postgresql":
                self._reset_postgresql(connection)
            elif vendor == "mysql":
                self._reset_mysql(connection)
            elif vendor == "sqlite":
                self._reset_sqlite(connection, db_alias)
            else:
                raise CommandError(f"Unsupported database vendor: {vendor}")
        except Exception as e:
            raise CommandError(f"Error during database reset: {e}")

        self.stdout.write(self.style.SUCCESS("Database schema cleared."))

        # Re-run migrations
        self.stdout.write(self.style.NOTICE("Running migrations..."))
        call_command("migrate", database=db_alias, interactive=False)
        self.stdout.write(self.style.SUCCESS("Migrations completed successfully."))

        if seed:
            self.seed_data()

    def _reset_postgresql(self, connection):
        """
        PostgreSQL reset: Drop public schema and recreate it.
        This effectively drops all tables, types, and functions.
        """
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")
            cursor.execute("GRANT ALL ON SCHEMA public TO public;")
            # If the user is not a superuser, they might need explicit grants
            # on the public schema if they are the owner.
            db_user = connection.settings_dict.get("USER")
            if db_user:
                cursor.execute(f"GRANT ALL ON SCHEMA public TO {db_user};")

    def _reset_mysql(self, connection):
        """
        MySQL reset: Disable FK checks and drop all tables.
        """
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")

            # Get all tables
            cursor.execute("SHOW TABLES;")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                self.stdout.write(f"Dropping table: {table}")
                cursor.execute(f"DROP TABLE IF EXISTS `{table}` CASCADE;")

            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    def _reset_sqlite(self, connection, db_alias):
        """
        SQLite reset: Delete the database file.
        """
        db_name = connection.settings_dict["NAME"]

        if db_name == ":memory:":
            self.stdout.write("Memory database detected, no file to delete.")
            # Closing the connection is enough for :memory: but call_command('migrate')
            # will open a new one anyway. For :memory: we might just want to
            # let it be, but technically it's already "reset" if we close and reopen.
            # However, for consistency, we can drop tables if it's already open.
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
                for table in tables:
                    cursor.execute(f'DROP TABLE IF EXISTS "{table}";')
                cursor.execute("PRAGMA foreign_keys = ON;")
            return

        if os.path.exists(db_name):
            # We need to close the connection before deleting the file
            connection.close()
            try:
                os.remove(db_name)
                self.stdout.write(f"Deleted SQLite file: {db_name}")
            except OSError as e:
                self.stdout.write(self.style.WARNING(f"Could not delete SQLite file {db_name}: {e}"))
                # Fallback to dropping tables
                self.stdout.write("Falling back to dropping tables...")
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA foreign_keys = OFF;")
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
                    for table in tables:
                        cursor.execute(f'DROP TABLE IF EXISTS "{table}";')
                    cursor.execute("PRAGMA foreign_keys = ON;")
        else:
            self.stdout.write(f"SQLite file not found at {db_name}, nothing to delete.")

    def seed_data(self):
        """
        Optional hook for seeding data after reset.
        """
        self.stdout.write(self.style.NOTICE("Seeding data..."))
        # TODO: Implement actual seeding logic here or call a separate command
        self.stdout.write("TODO: Implement seed_data() hook.")
        self.stdout.write(self.style.SUCCESS("Seeding completed (simulated)."))
