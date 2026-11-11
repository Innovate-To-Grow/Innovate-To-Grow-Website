"""Staging an upload as a batch, and keeping the admin's choices: saves, forged and stale posts, bulk commands."""

import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.batches import StaleVersion, save_choices, stored_analysis
from apps.authn.services.members.import_.review.choices import NEEDS_NAMES
from apps.authn.services.members.import_.review.selection import ForgedSelection
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


class BulkChoiceTests(BatchTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")
        self.email(self.ada, "ada.work@example.com", verified=True)
        self.home = self.email(self.ada, "ada.home@example.com", verified=False)
        self.email(self.grace, "grace.work@example.com", verified=False)
        rows = [row("ada.work@example.com"), row("grace.work@example.com", First_Name="Grace", Last_Name="Hopper")]
        self.batch = self.stage(rows, self.admin)

    def bulk(self, conflict, value, batch=None):
        return self.save(batch or self.batch, command=f"bulk:{conflict}", bulk={conflict: value})

    def test_a_bulk_choice_is_applied_where_allowed_and_the_other_rows_are_listed(self):
        outcome = self.bulk("address_not_primary", "update_make_primary")

        self.assertEqual(self.choices(self.batch), {2: ("update_make_primary", []), 3: ("skip", [])})
        self.assertEqual(outcome.kept, [f"Row 3: {UNVERIFIED}"])
        self.assertEqual(
            (outcome.message, outcome.level), ("Applied to 1 row(s). 1 row(s) kept their choice.", "warning")
        )
        event = self.batch.activity[-1]
        self.assertEqual(
            (event["action"], event["detail"]), ("bulk", "bulk address_not_primary=update_make_primary: 1 rows, 1 kept")
        )
        self.assertEqual(self.batch.rows.get(row_number=2).chosen_by, self.admin)
        self.assertEqual(self.version(self.batch), 1)

    def test_bulk_update_and_bulk_skip(self):
        outcome = self.bulk("address_not_primary", "update")
        self.assertEqual((outcome.message, outcome.level, outcome.kept), ("Applied to 2 row(s).", "success", []))
        self.assertEqual(self.choices(self.batch), {2: ("update", []), 3: ("update", [])})

        self.bulk("address_not_primary", "skip")
        self.assertEqual(self.choices(self.batch), {2: ("skip", []), 3: ("skip", [])})

    def test_a_bulk_choice_keeps_the_ticks_that_still_apply(self):
        tick = f"R1:{self.home.pk}"
        self.save(self.batch, {2: ("update", [tick])})

        self.bulk("address_not_primary", "update_make_primary")

        self.assertEqual(self.choices(self.batch)[2], ("update_make_primary", [tick]))

    def test_choices_for_one_row_at_a_time_are_refused_in_bulk(self):
        cases = [
            ("name_differs", "update_same_person"),
            ("ambiguous_address", "use_member"),
            ("uuid_email_mismatch", f"use_member:{self.ada.pk}"),
            ("privileged_target", "skip"),
            ("address_not_primary", "create"),
            ("address_not_primary", ""),
        ]
        for conflict, value in cases:
            with self.subTest(conflict=conflict, value=value):
                with self.assertRaisesMessage(
                    ForgedSelection, f"{value!r} can't be applied to every row of this group"
                ):
                    self.bulk(conflict, value)
        self.assertEqual(self.version(self.batch), 0)

    def test_bulk_create_claim(self):
        first = ContactEmail.objects.create(member=None, email_address="loose.one@example.com")
        ContactEmail.objects.create(member=None, email_address="loose.two@example.com")
        rows = [row("loose.one@example.com"), row("loose.two@example.com", Last_Name=None)]
        batch = self.stage(rows, self.admin)

        outcome = self.bulk("unlinked_address", "create_claim", batch)

        self.assertEqual(self.choices(batch), {2: (f"create_claim:{first.pk}", []), 3: ("skip", [])})
        self.assertEqual(outcome.kept, [f"Row 3: {NEEDS_NAMES}"])

    def test_bulk_ignore_uuid(self):
        rows = [
            [*row("ada@example.com", Organization="Engines"), str(uuid.uuid4())],
            [*row("grace@example.com", First_Name="Someone", Last_Name="Else"), str(uuid.uuid4())],
        ]
        batch = self.stage(rows, self.admin, headers=UUID_HEADERS)

        outcome = self.bulk("uuid_not_found", "ignore_uuid", batch)

        self.assertEqual(self.choices(batch), {2: ("ignore_uuid", []), 3: ("skip", [])})
        self.assertEqual(outcome.kept, ["Row 3: The sheet's name differs from the member's; decide on this row alone"])

    def test_bulk_update_in_skip_mode(self):
        rows = [
            row("ada@example.com", Organization="Engines"),
            row("grace@example.com", First_Name="Grace", Last_Name="Hopper"),
        ]
        batch = self.stage(rows, self.admin, mode=SKIP_EXISTING)

        self.bulk("exists_but_skip_mode", "update", batch)

        self.assertEqual(self.choices(batch), {2: ("update", []), 3: ("update", [])})

    def test_use_the_first_usable_row_of_every_repeat_group(self):
        self.member("Bob", "Babbage", "bob@example.com")
        rows = [
            row("ada@example.com", Organization="A"),
            row("ADA@example.com", Organization="B"),
            row("grace@example.com", First_Name="Someone", Last_Name="Else"),
            row("grace@example.com", First_Name="Grace", Last_Name="Hopper", Organization="C"),
            row("bob@example.com", First_Name="Xavier", Last_Name="Young"),
            row("bob@example.com", First_Name="Zed", Last_Name="West"),
        ]
        batch = self.stage(rows, self.admin)

        outcome = self.bulk("duplicate_in_sheet", "use_first", batch)

        self.assertEqual(
            {number: choice for number, (choice, _ticks) in self.choices(batch).items()},
            {2: "use_row", 3: "skip", 4: "skip", 5: "use_row", 6: "skip", 7: "skip"},
        )
        self.assertEqual(outcome.kept, ["Rows 6, 7: no row of the group can be used on its own"])
        self.assertEqual(
            (outcome.message, outcome.level),
            ("Used the first usable row of 2 group(s). 1 group(s) stay skipped.", "warning"),
        )
        self.assertEqual(batch.activity[-1]["detail"], "bulk use first: 2 groups")

    def test_reset_puts_a_conflict_back_on_skip(self):
        self.save(self.batch, {2: ("update", [f"R1:{self.home.pk}"]), 3: ("update", [])})

        outcome = self.save(self.batch, command="reset:address_not_primary")

        self.assertEqual(self.choices(self.batch), {2: ("skip", []), 3: ("skip", [])})
        self.assertEqual(outcome.message, "2 row(s) reset to Skip.")
        self.assertEqual(self.batch.activity[-1]["detail"], "reset address_not_primary: 2 rows")

    def test_skip_every_row_that_needs_a_decision(self):
        batch = self.stage([row("ada.work@example.com"), row("new@example.com"), row("nina@example.com")], self.admin)
        self.save(batch, {2: ("update", []), 4: ("skip", [])})

        outcome = self.save(batch, command="skipall")

        self.assertEqual(self.choices(batch), {2: ("skip", []), 3: ("create", []), 4: ("skip", [])})
        self.assertEqual(outcome.message, "Every row that needs a decision (1) is set to Skip.")
        self.assertEqual(self.version(batch), 2)

    def test_tick_every_item_of_one_kind(self):
        ContactEmail.objects.filter(email_address="grace@example.com").update(verified=False)
        ContactEmail.objects.filter(email_address="grace.work@example.com").update(verified=True)
        bob = self.member("Bob", "Babbage", "bob@example.com")
        self.email(bob, "bob.home@example.com")
        rows = [
            row("ada@example.com"),
            row("grace@example.com", First_Name="Grace", Last_Name="Hopper"),
            row("bob@example.com", First_Name="Bob", Last_Name="Babbage"),
        ]
        self.phone(self.ada, "2095550101")
        batch = self.stage(rows, self.admin)
        self.save(batch, {2: ("update", [f"R1:{self.home.pk}"]), 4: ("skip", [])})

        outcome = self.save(batch, command="tickall:R1")

        ticks = {number: ticks for number, (_choice, ticks) in self.choices(batch).items()}
        work = ContactEmail.objects.get(email_address="ada.work@example.com")
        self.assertEqual(set(ticks[2]), {f"R1:{work.pk}", f"R1:{self.home.pk}"})
        self.assertEqual((ticks[3], ticks[4]), ([], []))
        self.assertEqual((outcome.message, outcome.level), ("Ticked 1 item(s). 1 could not be ticked.", "warning"))
        self.assertEqual(batch.activity[-1]["detail"], "tick all R1: 1 ticked, 1 disabled")
