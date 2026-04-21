from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings


class ResetDBCommandTest(TestCase):
    @override_settings(DEBUG=True)
    def test_missing_flags(self):
        """Test that the command fails without --force and --confirm."""
        out = StringIO()
        with self.assertRaises(CommandError) as cm:
            call_command("resetdb", stdout=out)
        self.assertIn(
            "Destructive command requires --force and --confirm RESET_DB",
            str(cm.exception),
        )

    @override_settings(DEBUG=True)
    def test_wrong_confirm_string(self):
        """Test that the command fails with wrong confirmation string."""
        out = StringIO()
        with self.assertRaises(CommandError) as cm:
            call_command("resetdb", "--force", "--confirm=WRONG", stdout=out)
        self.assertIn(
            "Destructive command requires --force and --confirm RESET_DB",
            str(cm.exception),
        )

    @override_settings(DEBUG=False)
    def test_refuse_in_production(self):
        """Test that the command refuses to run when DEBUG=False."""
        out = StringIO()
        with self.assertRaises(CommandError) as cm:
            call_command("resetdb", "--force", "--confirm=RESET_DB", stdout=out)
        self.assertIn(
            "Command restricted to DEBUG=True. Use --allow-production to override.",
            str(cm.exception),
        )

    @override_settings(DEBUG=False)
    def test_allow_production_flag_bypasses_debug_guard(self):
        """--allow-production must bypass the DEBUG=False guard.

        The destructive helpers (reset_* / delete_migration_files / call_command)
        are patched out so the test stays in dev without mutating the schema.
        """
        from unittest.mock import patch

        with (
            patch("core.management.commands.resetdb.delete_migration_files"),
            patch("core.management.commands.resetdb.reset_postgresql"),
            patch("core.management.commands.resetdb.reset_mysql"),
            patch("core.management.commands.resetdb.reset_sqlite"),
            patch("core.management.commands.resetdb.create_default_admin"),
            patch("core.management.commands.resetdb.seed_archive_data"),
            patch("core.management.commands.resetdb.call_command"),
        ):
            out = StringIO()
            # This must not raise CommandError("Command restricted to DEBUG=True").
            call_command(
                "resetdb",
                "--force",
                "--confirm=RESET_DB",
                "--allow-production",
                stdout=out,
            )

    # TODO: Add integration tests that use a separate test database to verify
    # the actual SQL execution for each vendor (PostgreSQL, MySQL, SQLite).
    # This would require configuring these databases in the test environment.
