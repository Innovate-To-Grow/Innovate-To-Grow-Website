from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.services.members.import_.review import (
    analyse_rows,
    load_snapshot,
    run_import,
)
from apps.authn.services.members.import_.review.apply.execute import RowWriteError, log_batch, log_member_changes
from apps.authn.tests.services.members.import_.apply.test_apply import ApplyTestCase
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, read, row


class PermissionAtApplyTests(ApplyTestCase):
    def test_a_member_made_an_admin_after_the_review_goes_back_to_review(self):
        """Not for a permission (any Admin may update an Admin): the record the review showed changed."""
        batch = self.stage([row("ada@example.com", Organization="Engines")], self.admin)
        self.ada.is_staff = True
        self.ada.save()

        result = self.confirm(batch)

        self.assertEqual((result.status, result.rows), ("stale", [2]))
        stored = batch.rows.get()
        self.assertEqual((stored.status, stored.conflict, stored.choice), ("ready_update", "", "skip"))
        self.assertTrue(stored.changed_since_review)
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

    def test_a_revoked_change_permission_updates_nobody(self):
        """The change permission is withdrawn between the review and the confirm: no member may be updated."""
        batch = self.stage([row("ada@example.com", Organization="Engines")], self.admin)

        result = self.confirm(batch, can_update=False)

        self.ada.refresh_from_db()
        self.assertNotEqual(result.status, "applied", "the member was updated without the change permission")
        self.assertIsNone(self.ada.organization)


class RunImportTests(ImportTestCase):
    """``run_import``, the write step: what stops it, and what it schedules after the commit."""

    def analysed(self, rows):
        parsed = read(HEADERS, rows).rows
        snapshot = load_snapshot(parsed)
        return analyse_rows(parsed, snapshot, self.context()), snapshot

    def test_a_member_missing_from_the_locked_set_stops_the_import(self):
        analyses, snapshot = self.analysed([row("ada@example.com", Organization="Engines")])

        with self.assertRaisesMessage(RowWriteError, "Row 2: the member the review showed no longer exists"):
            with transaction.atomic():
                run_import(analyses, {}, snapshot, password_hash="!", members={})

        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

    def test_an_unlinked_address_taken_after_the_review_stops_the_import(self):
        loose = ContactEmail.objects.create(member=None, email_address="loose@example.com")
        rows = [row("nina@example.com", First_Name="Nina", Last_Name="New"), row("loose@example.com")]
        analyses, snapshot = self.analysed(rows)
        ContactEmail.objects.filter(pk=loose.pk).update(member=self.ada, email_type="other")

        with self.assertRaisesMessage(
            RowWriteError, "Row 3: the contact email with no member was taken or removed after the review"
        ):
            with transaction.atomic():
                run_import(analyses, {3: (f"create_claim:{loose.pk}", [])}, snapshot, password_hash="!", members={})

        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.assertEqual(Member.objects.filter(first_name="Ada").count(), 1)

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_new_members_schedule_one_sheet_sync_after_the_commit(self, schedule):
        rows = [row("nina@example.com", First_Name="Nina", Last_Name="New"), row("omar@example.com", First_Name="Omar")]

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.apply(rows)

        self.assertEqual(len(callbacks), 1)
        schedule.assert_called_once_with()

    def test_history_is_written_only_with_an_actor(self):
        batch = MemberImportBatch.objects.create(file_name="x.xlsx", file_sha256="0" * 64, expires_at=timezone.now())

        log_member_changes(None, [(self.ada, False, "changed")])
        log_member_changes(self.ada.pk, [])
        log_batch(None, batch, "Applied")

        self.assertFalse(LogEntry.objects.exists())
