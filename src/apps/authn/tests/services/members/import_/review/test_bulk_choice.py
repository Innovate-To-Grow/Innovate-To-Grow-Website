import uuid

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.analysis.choices import NEEDS_NAMES
from apps.authn.services.members.import_.review.staging.selection import ForgedSelection
from apps.authn.tests.services.members.import_.helpers import row
from apps.authn.tests.services.members.import_.reading.test_batches import UNVERIFIED, UUID_HEADERS, BatchTestCase


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
