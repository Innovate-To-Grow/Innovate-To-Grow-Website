"""authn 0024: one Admin role (inactive accounts lose Admin, the superuser flag mirrors staff, invitations cancelled)."""

import contextlib
import io

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class SingleAdminRoleMigrationTests(TransactionTestCase):
    migrate_from = [("authn", "0023_member_import_batch")]
    migrate_to = [("authn", "0024_single_admin_role")]

    def tearDown(self):
        # Back to the latest schema for the tests that run after this one (see test_registration_pending_migration).
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_rows_are_brought_to_the_single_admin_role(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldMember = old_apps.get_model("authn", "Member")
        OldInvitation = old_apps.get_model("authn", "AdminInvitation")

        def member(**flags):
            return OldMember.objects.create(**flags).pk

        master = member(is_active=True, is_staff=True, is_superuser=True)
        limited_staff = member(is_active=True, is_staff=True, is_superuser=False, admin_apps=["cms"])
        inactive_master = member(is_active=False, is_staff=True, is_superuser=True)
        inactive_staff = member(is_active=False, is_staff=True, is_superuser=False)
        stray_superuser = member(is_active=True, is_staff=False, is_superuser=True)
        regular = member(is_active=True, is_staff=False, is_superuser=False)
        inactive_regular = member(is_active=False, is_staff=False, is_superuser=False)

        expires = timezone.now() + timezone.timedelta(days=7)
        invitations = {
            status: OldInvitation.objects.create(
                email=f"{status}@example.com", token=f"token-{status}", status=status, expires_at=expires
            ).pk
            for status in ("pending", "accepted", "expired", "cancelled")
        }

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            MigrationExecutor(connection).migrate(self.migrate_to)
        new_apps = MigrationExecutor(connection).loader.project_state(self.migrate_to).apps
        NewMember = new_apps.get_model("authn", "Member")
        NewInvitation = new_apps.get_model("authn", "AdminInvitation")

        def flags(pk):
            row = NewMember.objects.get(pk=pk)
            return row.is_active, row.is_staff, row.is_superuser

        self.assertEqual(flags(master), (True, True, True))
        self.assertEqual(flags(limited_staff), (True, True, True))
        self.assertEqual(flags(inactive_master), (False, False, False))
        self.assertEqual(flags(inactive_staff), (False, False, False))
        self.assertEqual(flags(stray_superuser), (True, False, False))
        self.assertEqual(flags(regular), (True, False, False))
        self.assertEqual(flags(inactive_regular), (False, False, False))

        statuses = {status: NewInvitation.objects.get(pk=pk).status for status, pk in invitations.items()}
        self.assertEqual(
            statuses, {"pending": "cancelled", "accepted": "accepted", "expired": "expired", "cancelled": "cancelled"}
        )

        # The log names the changed accounts by id only.
        log = out.getvalue()
        self.assertIn("Inactive accounts that lost Admin (2)", log)
        self.assertIn("Staff accounts that became full Admins (1)", log)
        self.assertIn(str(limited_staff), log)
        self.assertIn("Non-staff accounts whose superuser flag was cleared (1)", log)
        self.assertIn("Pending admin invitations cancelled: 1", log)

    def test_the_migration_reverses_as_a_no_op(self):
        executor = MigrationExecutor(connection)
        with contextlib.redirect_stdout(io.StringIO()):
            executor.migrate(self.migrate_to)
        MigrationExecutor(connection).migrate(self.migrate_from)
        applied = MigrationExecutor(connection).loader.applied_migrations
        self.assertNotIn(("authn", "0024_single_admin_role"), applied)
