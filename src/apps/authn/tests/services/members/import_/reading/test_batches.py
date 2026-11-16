"""Staging an upload as a batch, and keeping the admin's choices: saves, forged and stale posts, bulk commands."""

from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.staging.batches import stored_analysis
from apps.authn.services.members.import_.review.staging.saving import save_choices
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]
UNVERIFIED = (
    "Not verified. The member can verify it on /account, or an admin can mark it verified in Contact Emails first."
)


class BatchTestCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.admin = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")

    def save(self, batch, posted=None, command="save", bulk=None, version=None):
        """``save_choices`` as the review page posts it (the current version unless given); ``batch`` is re-read."""
        batch.refresh_from_db()
        try:
            return save_choices(
                batch,
                user=self.admin,
                version=batch.choices_version if version is None else version,
                posted=posted or {},
                command=command,
                bulk=bulk or {},
            )
        finally:
            batch.refresh_from_db()

    @staticmethod
    def choices(batch) -> dict:
        return {stored.row_number: (stored.choice, stored.ticks) for stored in batch.rows.all()}

    @staticmethod
    def version(batch) -> int:
        batch.refresh_from_db()
        return batch.choices_version


class CreateBatchTests(BatchTestCase):
    def test_staging_writes_only_the_batch_and_its_rows(self):
        before = (Member.objects.count(), ContactEmail.objects.count())
        start = timezone.now()

        batch = self.stage(
            [row("ada@example.com", Organization="Engines"), row("new@example.com"), row(None)],
            self.admin,
            password="Default123!",
        )

        self.assertEqual((Member.objects.count(), ContactEmail.objects.count()), before)
        self.assertEqual((batch.status, batch.mode, batch.created_by), ("review", "update_existing", self.admin))
        self.assertEqual(
            (batch.file_name, batch.sheet_name, batch.row_count, batch.choices_version),
            ("upload.xlsx", "Members", 3, 0),
        )
        self.assertEqual(len(batch.file_sha256), 64)
        self.assertGreater(batch.file_size, 0)
        self.assertEqual(batch.columns["keys"][:3], ["primary_email", "first_name", "last_name"])
        self.assertTrue(check_password("Default123!", batch.default_password_hash))
        lifetime = timedelta(hours=24)
        self.assertTrue(start + lifetime <= batch.expires_at <= timezone.now() + lifetime)
        (event,) = batch.activity
        self.assertEqual(
            (event["action"], event["detail"], event["by"], event["by_name"]),
            ("upload", "upload.xlsx: 3 rows", str(self.admin.pk), "I2G Master"),
        )

    def test_each_row_is_stored_with_its_analysis_and_default_choice(self):
        batch = self.stage(
            [row("ada@example.com", Organization="Engines"), row("new@example.com"), row(None)], self.admin
        )

        rows = {stored.row_number: stored for stored in batch.rows.all()}
        self.assertEqual(
            [(r.status, r.conflict, r.choice, r.ticks) for r in rows.values()],
            [("ready_update", "", "update", []), ("ready_create", "", "create", []), ("invalid", "", "skip", [])],
        )
        self.assertEqual((rows[2].target_member, rows[3].target_member, rows[4].target_member), (self.ada, None, None))
        self.assertEqual(rows[2].values["organization"], "Engines")
        self.assertEqual([item["value"] for item in rows[2].analysis["options"]], ["update", "skip"])
        self.assertEqual(rows[2].analysis["default"], "update")
        self.assertEqual(list(rows[2].candidates["members"]), [str(self.ada.pk)])
        self.assertEqual(len(rows[2].fingerprint), 64)
        self.assertEqual(rows[4].analysis["invalid"], "Missing primary email")
        self.assertEqual((rows[2].chosen_by, rows[2].chosen_at, rows[2].outcome), (None, None, ""))

    def test_no_password_keeps_no_hash(self):
        batch = self.stage([row("new@example.com")], self.admin)

        self.assertEqual(batch.default_password_hash, "")

    def test_skip_mode_is_stored_and_its_rows_start_on_skip(self):
        batch = self.stage([row("ada@example.com", Organization="Engines")], self.admin, mode=SKIP_EXISTING)

        stored = batch.rows.get()
        self.assertEqual(batch.mode, "skip_existing")
        self.assertEqual(
            (stored.status, stored.conflict, stored.choice), ("needs_decision", "exists_but_skip_mode", "skip")
        )

    def test_a_stored_row_reads_back_as_the_analysis_it_was_reviewed_with(self):
        self.email(self.ada, "ada.work@example.com", verified=True)
        headers = [*HEADERS, "When Started"]
        cells_row = [*row("ada.work@example.com", Organization="Engines"), "2024-01-15"]
        analysis = self.analyse_one(cells_row, headers)

        batch = self.stage([cells_row], self.admin, headers=headers)

        stored = stored_analysis(batch.rows.get())
        self.assertEqual(stored.values, analysis.values)
        self.assertIsNotNone(stored.values["date_joined"])
        self.assertEqual(
            (stored.status, stored.conflict, stored.default, stored.fingerprint),
            (analysis.status, analysis.conflict, analysis.default, analysis.fingerprint),
        )
        self.assertEqual(
            (stored.facts, stored.options, stored.risky), (analysis.facts, analysis.options, analysis.risky)
        )
        self.assertEqual((stored.warnings, stored.slice), (analysis.warnings, analysis.slice))
