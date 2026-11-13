"""Applying a reviewed batch (``apply_batch``): all or nothing, once, and only as reviewed.

The apply re-reads every record the review read. A row whose records changed goes back to review with its choice
reset; a stale or refused apply writes nothing; a row that fails to write rolls the whole import back and leaves the
reason on the batch. Permissions are checked again with the actor's rights at apply time.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.services.members.import_ import contacts as contacts_module
from apps.authn.services.members.import_.contacts import ContactWriteError
from apps.authn.services.members.import_.review import (
    analyse_rows,
    apply_batch,
    load_snapshot,
    run_import,
    save_choices,
)
from apps.authn.services.members.import_.review.execute import RowWriteError, log_batch, log_member_changes
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, read, row


def not_privileged(member) -> bool:
    return not (member.is_staff or member.is_superuser)


class ApplyTestCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.admin = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")

    def choose(self, batch, posted):
        batch.refresh_from_db()
        save_choices(batch, user=self.admin, version=batch.choices_version, posted=posted, command="save", bulk={})
        batch.refresh_from_db()

    def confirm(self, batch, version=None, **context):
        batch.refresh_from_db()
        version = batch.choices_version if version is None else version
        result = apply_batch(batch.pk, user=self.admin, version=version, ctx=self.context(**context))
        batch.refresh_from_db()
        return result


class ApplyTests(ApplyTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")
        self.work = self.email(self.grace, "grace.work@example.com", verified=True)
        rows = [
            row("ada@example.com", Organization="Engines"),
            row("nina@example.com", First_Name="Nina", Last_Name="New"),
            row(None),
            row("grace.work@example.com", First_Name="Grace", Last_Name="Hopper", Title="Admiral"),
        ]
        self.batch = self.stage(rows, self.admin, password="Default123!")

    def test_every_row_is_written_and_its_outcome_recorded(self):
        result = self.confirm(self.batch)

        self.assertEqual((result.status, result.message, result.rows), ("applied", "", []))
        self.ada.refresh_from_db()
        self.grace.refresh_from_db()
        self.assertEqual((self.ada.organization, self.grace.title), ("Engines", None))
        nina = Member.objects.get(first_name="Nina")
        self.assertTrue(check_password("Default123!", nina.password))
        batch = self.batch
        self.assertEqual(
            (batch.status, batch.applied_by, batch.default_password_hash, batch.last_error),
            ("applied", self.admin, "", ""),
        )
        self.assertIsNotNone(batch.applied_at)
        self.assertEqual(
            batch.summary, {"outcomes": {"updated": 1, "created": 1, "not_imported": 1, "skipped": 1}, "risky": {}}
        )
        self.assertEqual(
            (batch.activity[-1]["action"], batch.activity[-1]["detail"]),
            ("apply", "1 created, 1 updated, 0 no change, 1 skipped, 1 not imported"),
        )
        rows = {stored.row_number: stored for stored in batch.rows.all()}
        self.assertEqual(
            [(r.outcome, r.result_member) for r in rows.values()],
            [("updated", self.ada), ("created", nina), ("not_imported", None), ("skipped", self.grace)],
        )
        self.assertEqual(rows[2].outcome_detail, "Organization: '' → 'Engines'")
        self.assertEqual(rows[4].outcome_detail, "Missing primary email")
        self.assertEqual(rows[5].outcome_detail, rows[5].analysis["why"])
        self.assertEqual(mail.outbox, [])

    def test_history_is_written_for_each_member_and_for_the_batch(self):
        self.confirm(self.batch)

        nina = Member.objects.get(first_name="Nina")
        updated = LogEntry.objects.get(object_id=str(self.ada.pk))
        created = LogEntry.objects.get(object_id=str(nina.pk))
        short = self.batch.short_id
        self.assertEqual((updated.action_flag, updated.user_id), (CHANGE, self.admin.pk))
        self.assertEqual(
            updated.change_message,
            f"Member import {short}, row 2: matched by primary email; Organization: '' → 'Engines'",
        )
        self.assertEqual(
            (created.action_flag, created.change_message), (ADDITION, f"Created by member import {short}, row 3")
        )
        batch_entry = LogEntry.objects.get(object_id=str(self.batch.pk))
        self.assertIn("Applied: 1 created, 1 updated", batch_entry.change_message)

    def test_a_second_apply_finds_the_batch_applied(self):
        self.confirm(self.batch)

        again = self.confirm(self.batch)

        self.assertEqual(again.status, "already")
        self.assertEqual(Member.objects.filter(first_name="Nina").count(), 1)
        self.assertEqual(self.batch.activity[-1]["action"], "apply")

    def test_an_outdated_version_is_refused(self):
        result = self.confirm(self.batch, version=5)

        self.assertEqual(
            (result.status, result.message),
            (
                "refused",
                "The choices changed after this page was loaded (in another tab?). Check the summary and confirm "
                "again.",
            ),
        )
        self.assertEqual(self.batch.status, "review")
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())

    def test_an_expired_review_is_refused(self):
        MemberImportBatch.objects.filter(pk=self.batch.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

        result = self.confirm(self.batch)

        self.assertEqual(
            (result.status, result.message),
            ("refused", "This review has expired. Upload the file again to start a new one."),
        )
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())

    def test_a_record_changed_after_the_review_sends_its_row_back(self):
        self.choose(self.batch, {5: ("update", [])})
        version = self.batch.choices_version
        ContactEmail.objects.filter(pk=self.work.pk).update(subscribe=False)

        result = self.confirm(self.batch)

        self.assertEqual(
            (result.status, result.message, result.rows), ("stale", "1 row(s) changed since the review", [5])
        )
        self.ada.refresh_from_db()
        self.grace.refresh_from_db()
        self.assertEqual((self.ada.organization, self.grace.title), (None, None))
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        stale = self.batch.rows.get(row_number=5)
        self.assertEqual((stale.choice, stale.chosen_by, stale.changed_since_review), ("skip", None, True))
        self.assertFalse(self.batch.rows.get(row_number=2).changed_since_review)
        self.assertEqual((self.batch.status, self.batch.choices_version), ("review", version + 1))
        self.assertEqual(
            self.batch.last_error,
            "Nothing was imported: the records of 1 row(s) changed since you reviewed them (rows 5). Their choices "
            "were reset; check them and confirm again.",
        )
        self.assertEqual(self.batch.activity[-1]["action"], "stale")

    def test_a_member_signing_in_does_not_make_the_review_stale(self):
        Member.objects.filter(pk=self.ada.pk).update(last_login=timezone.now())

        self.assertEqual(self.confirm(self.batch).status, "applied")

    def test_a_warning_that_changed_since_the_review_sends_its_row_back(self):
        # A review staged under an older rule showed no warning on row 3; the apply's fresh analysis sets its Secondary
        # Email aside (V8). The row goes back to review instead of applying a plan nobody saw.
        ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("one@example.com", First_Name="One", Secondary_Email="lab@example.com"),
            row("two@example.com", First_Name="Two", Secondary_Email="lab@example.com"),
        ]
        batch = self.stage(rows, self.admin)
        batch.rows.filter(row_number=3).update(warnings=[])

        result = self.confirm(batch)

        self.assertEqual((result.status, result.rows), ("stale", [3]))
        self.assertFalse(Member.objects.filter(first_name__in=["One", "Two"]).exists())
        stale = batch.rows.get(row_number=3)
        self.assertEqual((stale.choice, stale.changed_since_review), ("skip", True))
        self.assertEqual([warning["code"] for warning in stale.warnings], ["V8"])
        self.assertFalse(batch.rows.get(row_number=2).changed_since_review)

    def test_choices_with_a_problem_are_refused(self):
        batch = self.stage(
            [row("ada@example.com", Organization="A"), row("ADA@example.com", Organization="B")], self.admin
        )
        self.choose(batch, {2: ("use_row", []), 3: ("use_row", [])})

        result = self.confirm(batch)

        self.assertEqual(
            (result.status, result.message),
            (
                "refused",
                f"Rows 2 and 3 would all change Ada Lovelace (member {self.ada.pk}). Choose one of them and skip the "
                "others.",
            ),
        )
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

    @patch(
        "apps.authn.services.members.import_.review.execute.contacts.add_phone",
        side_effect=ContactWriteError("the number was taken after the review"),
    )
    def test_a_row_that_fails_to_write_rolls_everything_back(self, _add_phone):
        batch = self.stage(
            [
                row("nina@example.com", First_Name="Nina", Last_Name="New"),
                row("ada@example.com", Phone_Number="2095550199"),
            ],
            self.admin,
        )

        result = self.confirm(batch)

        self.assertEqual(
            (result.status, result.message, result.rows), ("error", "Row 3: the number was taken after the review", [3])
        )
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.assertEqual(batch.status, "review")
        self.assertEqual(batch.last_error, "Nothing was imported. Row 3: the number was taken after the review")
        self.assertEqual(
            (batch.activity[-1]["action"], batch.activity[-1]["detail"]),
            ("error", "Row 3: the number was taken after the review"),
        )

    def test_a_database_error_sends_the_batch_back_to_review(self):
        """An address another request stored after the re-read trips the unique constraint: nothing is written."""
        add_email = contacts_module.add_email

        def racing_add_email(member, data):
            ContactEmail.objects.create(member=None, email_address=data["address"])  # the other request's insert
            add_email(member, data)

        batch = self.stage(
            [
                row("nina@example.com", First_Name="Nina", Last_Name="New"),
                row("ada@example.com", Organization="Engines", Secondary_Email="ada.new@example.com"),
            ],
            self.admin,
        )

        with (
            patch("apps.authn.services.members.import_.review.execute.contacts.add_email", racing_add_email),
            self.assertLogs("apps.authn.services.members.import_.review.apply", level="ERROR"),
        ):
            result = self.confirm(batch)

        self.assertEqual(result.status, "error")
        self.assertTrue(result.message.startswith("A database error stopped the import (IntegrityError)"))
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.assertFalse(ContactEmail.objects.filter(email_address="ada.new@example.com").exists())
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
        self.assertEqual(batch.status, "review")
        self.assertTrue(batch.last_error.startswith("Nothing was imported. A database error stopped the import"))
        self.assertEqual(batch.activity[-1]["action"], "error")


class PermissionAtApplyTests(ApplyTestCase):
    def test_a_member_who_became_staff_goes_back_to_review_for_a_non_master(self):
        batch = self.stage([row("ada@example.com", Organization="Engines")], self.admin, can_manage=not_privileged)
        Member.objects.filter(pk=self.ada.pk).update(is_staff=True)

        result = self.confirm(batch, can_manage=not_privileged)

        self.assertEqual((result.status, result.rows), ("stale", [2]))
        stored = batch.rows.get()
        self.assertEqual((stored.conflict, stored.choice), ("privileged_target", "skip"))
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
