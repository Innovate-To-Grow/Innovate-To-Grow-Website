import os
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.management.commands import resetdb_helpers as helpers
from apps.core.tests.commands.resetdb.test_resetdb_helpers import FakeCommand, _cursor_mock


class ResetSqliteTest(TestCase):
    def test_memory_database_drops_tables(self):
        cmd = FakeCommand()
        connection = MagicMock()
        connection.settings_dict = {"NAME": ":memory:"}

        with patch("apps.core.management.commands.resetdb_helpers.drop_sqlite_tables") as drop:
            helpers.reset_sqlite(cmd, connection)

        drop.assert_called_once_with(connection)
        self.assertIn("Memory database detected.", cmd.stdout.text)

    def test_existing_file_is_deleted(self):
        cmd = FakeCommand()
        connection = MagicMock()
        connection.settings_dict = {"NAME": "/tmp/dev.sqlite3"}

        with (
            patch("apps.core.management.commands.resetdb_helpers.os.path.exists", return_value=True),
            patch("apps.core.management.commands.resetdb_helpers.os.remove") as remove,
        ):
            helpers.reset_sqlite(cmd, connection)

        connection.close.assert_called_once()
        remove.assert_called_once_with("/tmp/dev.sqlite3")
        self.assertIn("Deleted SQLite file: /tmp/dev.sqlite3", cmd.stdout.text)

    def test_delete_failure_falls_back_to_drop_tables(self):
        cmd = FakeCommand()
        connection = MagicMock()
        connection.settings_dict = {"NAME": "/tmp/dev.sqlite3"}

        with (
            patch("apps.core.management.commands.resetdb_helpers.os.path.exists", return_value=True),
            patch(
                "apps.core.management.commands.resetdb_helpers.os.remove",
                side_effect=OSError("locked"),
            ),
            patch("apps.core.management.commands.resetdb_helpers.drop_sqlite_tables") as drop,
        ):
            helpers.reset_sqlite(cmd, connection)

        drop.assert_called_once_with(connection)
        self.assertIn("Could not delete SQLite file: locked", cmd.stdout.text)

    def test_missing_file_writes_message(self):
        cmd = FakeCommand()
        connection = MagicMock()
        connection.settings_dict = {"NAME": "/tmp/missing.sqlite3"}

        with patch("apps.core.management.commands.resetdb_helpers.os.path.exists", return_value=False):
            helpers.reset_sqlite(cmd, connection)

        self.assertIn("SQLite file not found at /tmp/missing.sqlite3", cmd.stdout.text)

    def test_drop_sqlite_tables_skips_sequence_table(self):
        connection, cursor = _cursor_mock()
        connection.ops.quote_name.side_effect = lambda name: f'"{name.replace(chr(34), chr(34) * 2)}"'
        cursor.fetchall.return_value = [("members",), ("sqlite_sequence",)]

        helpers.drop_sqlite_tables(connection)

        executed = [c.args[0] for c in cursor.execute.call_args_list]
        self.assertIn("PRAGMA foreign_keys = OFF;", executed)
        self.assertIn('DROP TABLE IF EXISTS "members";', executed)
        self.assertNotIn('DROP TABLE IF EXISTS "sqlite_sequence";', executed)
        self.assertIn("PRAGMA foreign_keys = ON;", executed)


class RemovePycacheTest(TestCase):
    def test_removes_existing_pycache(self):
        with (
            patch("apps.core.management.commands.resetdb_helpers.os.path.exists", return_value=True),
            patch("apps.core.management.commands.resetdb_helpers.shutil.rmtree") as rmtree,
        ):
            helpers._remove_pycache("/fake/app/migrations")

        rmtree.assert_called_once_with(os.path.join("/fake/app/migrations", "__pycache__"))

    def test_noop_when_pycache_absent(self):
        with (
            patch("apps.core.management.commands.resetdb_helpers.os.path.exists", return_value=False),
            patch("apps.core.management.commands.resetdb_helpers.shutil.rmtree") as rmtree,
        ):
            helpers._remove_pycache("/fake/app/migrations")

        rmtree.assert_not_called()


class CreateDefaultAdminTest(TestCase):
    def test_creates_superuser_and_contact_email(self):
        from apps.authn.models import ContactEmail, Member

        cmd = FakeCommand()
        helpers.create_default_admin(cmd)

        member = Member.objects.get(first_name="Dev", last_name="Admin")
        self.assertTrue(member.is_superuser)
        contact = ContactEmail.objects.get(email_address__iexact="dev-admin@example.com")
        self.assertEqual(contact.member, member)
        self.assertTrue(contact.verified)
        self.assertIn("Created admin user:", cmd.stdout.text)

    def test_skips_when_flag_disabled(self):
        from apps.authn.models import Member

        cmd = FakeCommand()
        cmd.DEV_ADD_ADMIN_USER = False
        helpers.create_default_admin(cmd)

        self.assertFalse(Member.objects.filter(first_name="Dev").exists())
        self.assertIn("Skipping admin user creation", cmd.stdout.text)

    def test_skips_when_admin_email_exists(self):
        from apps.authn.models import ContactEmail, Member

        member = Member.objects.create(first_name="X", last_name="Y")
        ContactEmail.objects.create(
            member=member,
            email_address="dev-admin@example.com",
            email_type="primary",
            verified=True,
        )
        cmd = FakeCommand()
        helpers.create_default_admin(cmd)

        self.assertIn("already exists", cmd.stdout.text)
        # No new superuser was created.
        self.assertFalse(Member.objects.filter(first_name="Dev", last_name="Admin").exists())


class SeedArchiveDataTest(TestCase):
    def test_missing_directory_warns_and_returns(self):
        cmd = FakeCommand()
        with patch("apps.core.management.commands.resetdb_helpers.os.path.isdir", return_value=False):
            helpers.seed_archive_data(cmd)
        self.assertIn("Archive data directory not found", cmd.stdout.text)

    def test_dispatches_to_each_seeder(self):
        cmd = FakeCommand()
        with (
            patch("apps.core.management.commands.resetdb_helpers.os.path.isdir", return_value=True),
            patch("apps.core.management.commands.resetdb_helpers._seed_cms_pages") as cms,
            patch("apps.core.management.commands.resetdb_helpers._seed_menus") as menus,
            patch("apps.core.management.commands.resetdb_helpers._seed_footer") as footer,
        ):
            helpers.seed_archive_data(cmd)
        cms.assert_called_once_with(cmd)
        menus.assert_called_once_with(cmd)
        footer.assert_called_once_with(cmd)
