"""Retention of staged imports, and the end of a review: discard, expiry and repeat uploads.

``purge_member_imports``: a batch that was not applied (in review, discarded or expired) is deleted with its rows once
it expires; an applied batch loses its rows' sheet values and snapshots after ``values_retention_days`` and is deleted
after ``rows_retention_days``.
"""

from datetime import timedelta

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.authn.models import Member, MemberImportBatch, MemberImportRow
from apps.authn.services.members.import_.review import purge_member_imports
from apps.authn.services.members.import_.review.staging import purge
from apps.authn.tests.services.members.import_.helpers import ImportTestCase

Status = MemberImportBatch.Status
NOTHING = {"expired": 0, "blanked": 0, "deleted": 0}


class PurgeTestCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now()

    def batch(self, status=Status.REVIEW, *, expires_in=timedelta(hours=1), applied_ago=None, sha="0" * 64):
        """A batch with one row whose every kept field is filled in."""
        batch = MemberImportBatch.objects.create(
            file_name="members.xlsx",
            file_sha256=sha,
            status=status,
            expires_at=self.now + expires_in,
            applied_at=None if applied_ago is None else self.now - applied_ago,
        )
        MemberImportRow.objects.create(
            batch=batch,
            row_number=2,
            status="ready_update",
            values={"row": 2, "primary_email": "ada@example.com"},
            candidates={"members": {str(self.ada.pk): {"first_name": "Ada"}}},
            risky={str(self.ada.pk): [{"id": f"R7:{self.ada.pk}"}]},
            warnings=[{"code": "V5", "text": "Active cell 'x' is not TRUE or FALSE; it was ignored"}],
            choice="update",
            ticks=[f"R7:{self.ada.pk}"],
            target_member=self.ada,
            chosen_by=self.ada,
            outcome="updated",
            outcome_detail="Organization: '' → 'Engines'",
            result_member=self.ada,
        )
        return batch


class UnappliedBatchTests(PurgeTestCase):
    def test_unapplied_batches_are_deleted_with_their_rows_once_they_expire(self):
        for status in (Status.REVIEW, Status.DISCARDED, Status.EXPIRED):
            self.batch(status, expires_in=-timedelta(minutes=1))
        self.batch(expires_in=timedelta(0))
        live = self.batch()

        counts = purge_member_imports(now=self.now)

        self.assertEqual(counts, {**NOTHING, "expired": 4})
        self.assertEqual(list(MemberImportBatch.objects.all()), [live])
        self.assertEqual(list(MemberImportRow.objects.values_list("batch_id", flat=True)), [live.pk])

    def test_an_applied_batch_is_kept_after_its_review_would_have_expired(self):
        applied = self.batch(Status.APPLIED, expires_in=-timedelta(days=2), applied_ago=timedelta(days=1))

        self.assertEqual(purge_member_imports(now=self.now), NOTHING)
        self.assertTrue(MemberImportBatch.objects.filter(pk=applied.pk).exists())
        self.assertEqual(applied.rows.get().values["primary_email"], "ada@example.com")

    def test_now_defaults_to_the_current_time(self):
        self.batch(expires_in=-timedelta(minutes=1))

        self.assertEqual(purge_member_imports(), {**NOTHING, "expired": 1})
        self.assertFalse(MemberImportBatch.objects.exists())

    def test_a_batch_applied_after_its_id_was_read_is_kept(self):
        """The purge reads ids without a lock; an apply that started before ``expires_at`` may commit before the
        delete, and the locked re-read keeps that import."""
        applied = self.batch(expires_in=-timedelta(minutes=1))
        expired = self.batch(expires_in=-timedelta(minutes=1))
        query = MemberImportBatch.objects.filter(
            status__in=(Status.REVIEW, Status.DISCARDED, Status.EXPIRED), expires_at__lte=self.now
        )
        ids = list(query.values_list("pk", flat=True))
        MemberImportBatch.objects.filter(pk=applied.pk).update(status=Status.APPLIED, applied_at=self.now)

        self.assertEqual(purge._delete(query, ids), 1)

        self.assertEqual(list(MemberImportBatch.objects.all()), [applied])
        self.assertFalse(MemberImportBatch.objects.filter(pk=expired.pk).exists())
        self.assertEqual(applied.rows.count(), 1)


class AppliedBatchTests(PurgeTestCase):
    def test_sheet_values_are_blanked_after_the_values_retention(self):
        old = self.batch(Status.APPLIED, applied_ago=timedelta(days=30))
        recent = self.batch(Status.APPLIED, applied_ago=timedelta(days=29, hours=23))

        counts = purge_member_imports(now=self.now)

        self.assertEqual(counts, {**NOTHING, "blanked": 1})
        old.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual((old.values_purged_at, recent.values_purged_at), (self.now, None))
        blanked, kept = old.rows.get(), recent.rows.get()
        self.assertEqual((blanked.values, blanked.candidates, blanked.risky, blanked.warnings), ({}, {}, {}, []))
        self.assertEqual(
            (blanked.choice, blanked.ticks, blanked.chosen_by, blanked.outcome, blanked.result_member),
            ("update", [f"R7:{self.ada.pk}"], self.ada, "updated", self.ada),
        )
        # Outcome details name people (addresses, old and new values), so they go too; the outcome code stays.
        self.assertEqual((blanked.outcome_detail, blanked.analysis), ("", {}))
        self.assertEqual(kept.values["primary_email"], "ada@example.com")

    def test_values_are_blanked_only_once(self):
        old = self.batch(Status.APPLIED, applied_ago=timedelta(days=40))
        purge_member_imports(now=self.now)

        counts = purge_member_imports(now=self.now + timedelta(days=1))

        self.assertEqual(counts, NOTHING)
        old.refresh_from_db()
        self.assertEqual(old.values_purged_at, self.now)

    def test_applied_batches_are_deleted_after_the_rows_retention(self):
        self.batch(Status.APPLIED, applied_ago=timedelta(days=365))
        kept = self.batch(Status.APPLIED, applied_ago=timedelta(days=364))
        MemberImportBatch.objects.filter(pk=kept.pk).update(values_purged_at=self.now - timedelta(days=300))

        counts = purge_member_imports(now=self.now)

        self.assertEqual(counts, {"expired": 0, "blanked": 1, "deleted": 1})
        self.assertEqual(list(MemberImportBatch.objects.all()), [kept])
        self.assertEqual(MemberImportRow.objects.count(), 1)
        self.assertTrue(Member.objects.filter(pk=self.ada.pk).exists())


@override_settings(MEMBER_IMPORT={**settings.MEMBER_IMPORT, "purge_batch_size": 1})
class BoundedPurgeTests(PurgeTestCase):
    def test_max_passes_bounds_the_work(self):
        for _ in range(3):
            self.batch(expires_in=-timedelta(minutes=1))

        first = purge_member_imports(now=self.now, max_passes=2)
        self.assertEqual((first, MemberImportBatch.objects.count()), ({**NOTHING, "expired": 2}, 1))

        rest = purge_member_imports(now=self.now)
        self.assertEqual((rest, MemberImportBatch.objects.count()), ({**NOTHING, "expired": 1}, 0))

    def test_max_passes_counts_every_kind_of_pass(self):
        self.batch(expires_in=-timedelta(minutes=1))
        self.batch(Status.APPLIED, applied_ago=timedelta(days=31))

        self.assertEqual(purge_member_imports(now=self.now, max_passes=1), {**NOTHING, "expired": 1})
        self.assertEqual(purge_member_imports(now=self.now, max_passes=1), {**NOTHING, "blanked": 1})

    def test_should_stop_ends_the_purge_before_the_next_pass(self):
        for _ in range(3):
            self.batch(expires_in=-timedelta(minutes=1))
        answers = iter([False, True])

        self.assertEqual(purge_member_imports(now=self.now, should_stop=lambda: True), NOTHING)
        counts = purge_member_imports(now=self.now, should_stop=lambda: next(answers))

        self.assertEqual((counts, MemberImportBatch.objects.count()), ({**NOTHING, "expired": 1}, 2))
