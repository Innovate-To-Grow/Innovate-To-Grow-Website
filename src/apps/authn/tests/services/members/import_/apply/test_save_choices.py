import uuid
from datetime import timedelta

from django.utils import timezone

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.services.members.import_.review.staging.saving import ReviewClosed, StaleVersion
from apps.authn.services.members.import_.review.staging.selection import ForgedSelection
from apps.authn.tests.services.members.import_.helpers import row
from apps.authn.tests.services.members.import_.reading.test_batches import UUID_HEADERS, BatchTestCase


class SaveChoicesTests(BatchTestCase):
    def setUp(self):
        super().setUp()
        self.work = self.email(self.ada, "ada.work@example.com", verified=True)
        self.home = self.email(self.ada, "ada.home@example.com", verified=False)
        self.member("Grace", "Hopper", "grace@example.com")
        rows = [
            row("ada.work@example.com", Organization="Engines"),
            row("grace@example.com", First_Name="Someone", Last_Name="Else"),
            row("new@example.com"),
            row(None),
        ]
        self.batch = self.stage(rows, self.admin)
        self.tick = f"R1:{self.home.pk}"

    def test_a_saved_choice_records_who_chose_and_when(self):
        outcome = self.save(self.batch, {2: ("update", [self.tick])})

        self.assertEqual(
            (outcome.saved, outcome.message, outcome.level), (True, "Saved (1 row(s) changed).", "success")
        )
        rows = {stored.row_number: stored for stored in self.batch.rows.all()}
        self.assertEqual((rows[2].choice, rows[2].ticks, rows[2].chosen_by), ("update", [self.tick], self.admin))
        self.assertIsNotNone(rows[2].chosen_at)
        self.assertEqual({rows[n].chosen_by for n in (3, 4, 5)}, {None})
        self.assertEqual(self.version(self.batch), 1)

    def test_an_unchanged_post_changes_nothing(self):
        outcome = self.save(self.batch, {2: ("skip", []), 4: ("create", [])})

        self.assertEqual(outcome.message, "Saved (0 row(s) changed).")
        self.assertEqual(self.version(self.batch), 0)
        self.assertFalse(self.batch.rows.filter(chosen_by__isnull=False).exists())

    def test_a_stale_version_is_refused(self):
        with self.assertRaises(StaleVersion):
            self.save(self.batch, {2: ("update", [])}, version=7)

        self.assertEqual(self.choices(self.batch)[2], ("skip", []))
        self.assertEqual(self.version(self.batch), 0)

    def test_a_batch_that_is_no_longer_in_review_keeps_its_choices(self):
        """A save that waited for an apply or a discard in another request finds the batch final (same version)."""
        before = self.choices(self.batch)
        for status in ("applied", "discarded", "expired"):
            MemberImportBatch.objects.filter(pk=self.batch.pk).update(status=status)
            with self.assertRaisesMessage(ReviewClosed, "already applied, discarded or expired; nothing was saved"):
                self.save(self.batch, {2: ("update", [self.tick]), 4: ("skip", [])})
            self.assertEqual(self.choices(self.batch), before)
            self.assertEqual(self.version(self.batch), 0)
            self.assertFalse(self.batch.rows.filter(chosen_by__isnull=False).exists())

    def test_an_expired_review_keeps_its_choices(self):
        MemberImportBatch.objects.filter(pk=self.batch.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

        with self.assertRaises(ReviewClosed):
            self.save(self.batch, {2: ("update", [])})

        self.assertEqual(self.choices(self.batch)[2], ("skip", []))

    def test_a_choice_the_row_never_offered_saves_nothing(self):
        with self.assertRaisesMessage(ForgedSelection, "Row 3: 'create' is not one of this row's choices"):
            self.save(self.batch, {2: ("update", [self.tick]), 3: ("create", [])})

        self.assertEqual(self.choices(self.batch)[2], ("skip", []))
        self.assertEqual(self.version(self.batch), 0)

    def test_a_disabled_choice_is_refused(self):
        ContactEmail.objects.filter(pk=self.work.pk).update(verified=False)
        batch = self.stage([row("ada.work@example.com")], self.admin)

        with self.assertRaisesMessage(ForgedSelection, "Row 2: 'update_make_primary' is not one of this row's choices"):
            self.save(batch, {2: ("update_make_primary", [])})

    def test_an_unknown_tick_is_refused(self):
        forged = f"R1:{uuid.uuid4()}"

        with self.assertRaisesMessage(ForgedSelection, f"Row 2: {forged!r} is not one of this row's risky changes"):
            self.save(self.batch, {2: ("update", [forged])})

    def test_a_disabled_tick_is_refused(self):
        with self.assertRaisesMessage(
            ForgedSelection,
            "Row 2: Remove secondary ada.work@example.com (the Secondary Email cell is blank) can't be ticked",
        ):
            self.save(self.batch, {2: ("update", [f"R1:{self.work.pk}"])})

    def test_ticks_of_a_member_the_choice_does_not_update_are_dropped(self):
        self.save(self.batch, {2: ("update_make_primary", [self.tick])})

        self.save(self.batch, {2: ("skip", [self.tick])})

        self.assertEqual(self.choices(self.batch)[2], ("skip", []))

    def test_ticks_of_the_member_not_chosen_are_dropped(self):
        grace = Member.objects.get(first_name="Grace")
        theirs = self.email(grace, "grace.home@example.com")
        batch = self.stage([[*row("grace@example.com"), str(self.ada.pk)]], self.admin, headers=UUID_HEADERS)

        self.save(batch, {2: (f"use_member:{self.ada.pk}", [self.tick, f"R1:{theirs.pk}"])})

        self.assertEqual(self.choices(batch)[2], (f"use_member:{self.ada.pk}", [self.tick]))

    def test_a_missing_choice_or_tick_list_keeps_what_is_stored(self):
        self.save(self.batch, {2: ("update", [self.tick])})

        unchanged = self.save(self.batch, {2: (None, None)})
        self.assertEqual(
            (self.choices(self.batch)[2], unchanged.message), (("update", [self.tick]), "Saved (0 row(s) changed).")
        )

        self.save(self.batch, {2: (None, [])})
        self.assertEqual(self.choices(self.batch)[2], ("update", []))

    def test_a_row_that_cannot_be_imported_stays_on_skip(self):
        self.save(self.batch, {5: ("create", ["R1:anything"])})

        self.assertEqual(self.choices(self.batch)[5], ("skip", []))

    def test_an_unknown_command_is_a_plain_save(self):
        outcome = self.save(self.batch, {2: ("update", [])}, command="frobnicate")

        self.assertEqual(outcome.message, "Saved (1 row(s) changed).")
        self.assertEqual([event["action"] for event in self.batch.activity], ["upload"])
