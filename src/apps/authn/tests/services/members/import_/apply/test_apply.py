"""Applying a reviewed batch (``apply_batch``): all or nothing, once, and only as reviewed.

The apply re-reads every record the review read. A row whose records changed goes back to review with its choice
reset; a stale or refused apply writes nothing; a row that fails to write rolls the whole import back and leaves the
reason on the batch. Permissions are checked again with the actor's rights at apply time.
"""

from datetime import timedelta

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.utils import timezone

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.services.members.import_.review import (
    apply_batch,
    save_choices,
)
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row


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


class _ApplyCase(ApplyTestCase):
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


class ApplyTests(_ApplyCase):
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


UUID_HEADERS = ["Member UUID", *HEADERS]
UNKNOWN_UUID = "00000000-0000-4000-8000-000000000000"
