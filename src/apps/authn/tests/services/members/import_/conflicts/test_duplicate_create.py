from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_.review import (
    save_choices,
    stored_analysis,
)
from apps.authn.services.members.import_.review.staging.selection import selection_problems
from apps.authn.tests.services.members.import_.apply.test_apply import UNKNOWN_UUID, UUID_HEADERS, ApplyTestCase
from apps.authn.tests.services.members.import_.helpers import row


class _DuplicateCreateCase(ApplyTestCase):
    def uuid_row(self, uuid, primary, **cells):
        return [uuid, *row(primary, **cells)]

    def stage_uuid_rows(self, rows):
        return self.stage(rows, self.admin, headers=UUID_HEADERS)

    def problems(self, batch):
        """Every sentence the review lists for ``batch``'s saved choices (the confirm reports the first one)."""
        rows = list(batch.rows.order_by("row_number"))
        return selection_problems([stored_analysis(r) for r in rows], {r.row_number: (r.choice, r.ticks) for r in rows})


class DuplicateCreateTests(_DuplicateCreateCase):
    """Two rows that would create a member with the same Primary Email (ignoring case) are refused before the apply.

    A row whose Member UUID matches nobody (C5) is never put in a repeat group, so "Ignore the Member UUID" could make
    it create the same new address as another row: the exact address failed every confirm on the unique constraint,
    and a case variant made two members whose primary addresses differ only in letter case.
    """

    def test_a_row_matched_by_email_instead_of_its_uuid_and_a_new_row_with_the_same_address(self):
        batch = self.stage_uuid_rows(
            [
                self.uuid_row(UNKNOWN_UUID, "nina@example.com", First_Name="Nina", Last_Name="New"),
                self.uuid_row(None, "nina@example.com", First_Name="Nina", Last_Name="New"),
            ]
        )
        self.assertEqual(
            [(r.conflict, r.choice) for r in batch.rows.order_by("row_number")],
            [("uuid_not_found", "skip"), ("", "create")],
        )
        self.choose(batch, {2: ("ignore_uuid", [])})

        result = self.confirm(batch)

        self.assertEqual(
            (result.status, result.message),
            (
                "refused",
                "Rows 2 and 3 would all create a new member with nina@example.com. Choose one of them and skip the "
                "others.",
            ),
        )
        self.assertEqual(batch.status, "review")
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())

        self.choose(batch, {3: ("skip", [])})

        self.assertEqual(self.confirm(batch).status, "applied")
        self.assertEqual(Member.objects.filter(first_name="Nina").count(), 1)

    def test_two_rows_matched_by_email_instead_of_their_uuids(self):
        # For example a staging export, with "Ignore the Member UUID" applied to the whole group.
        batch = self.stage_uuid_rows(
            [
                self.uuid_row(UNKNOWN_UUID, "nina@example.com", First_Name="Nina", Last_Name="New"),
                self.uuid_row("00000000-0000-4000-8000-000000000001", "nina@example.com", First_Name="Nina"),
            ]
        )
        outcome = save_choices(
            batch,
            user=self.admin,
            version=batch.choices_version,
            posted={},
            command="bulk:uuid_not_found",
            bulk={"uuid_not_found": "ignore_uuid"},
        )
        self.assertEqual(outcome.message, "Applied to 2 row(s).")

        result = self.confirm(batch)

        self.assertEqual(result.status, "refused")
        self.assertEqual(
            result.message,
            "Rows 2 and 3 would all create a new member with nina@example.com. Choose one of them and skip the others.",
        )
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())

    def test_the_same_new_address_in_different_letter_case(self):
        batch = self.stage_uuid_rows(
            [
                self.uuid_row(UNKNOWN_UUID, "Nina@example.com", First_Name="Nina", Last_Name="New"),
                self.uuid_row(None, "nina@example.com", First_Name="Nina", Last_Name="New"),
            ]
        )
        self.choose(batch, {2: ("ignore_uuid", [])})

        result = self.confirm(batch)

        self.assertEqual(result.status, "refused")
        self.assertEqual(
            result.message,
            "Rows 2 and 3 would all create a new member with Nina@example.com / nina@example.com (the same address in "
            "different letter case). Choose one of them and skip the others.",
        )
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.assertFalse(ContactEmail.objects.filter(email_address__iexact="nina@example.com").exists())

    def test_a_repeat_group_used_twice_gets_one_sentence(self):
        batch = self.stage(
            [row("nina@example.com", First_Name="Nina", Last_Name="New"), row("NINA@example.com", First_Name="Nina")],
            self.admin,
        )
        self.choose(batch, {2: ("use_row", []), 3: ("use_row", [])})

        result = self.confirm(batch)

        self.assertEqual(
            (result.status, result.message),
            ("refused", "Rows 2 and 3 are the same person; use only one of them (rows 2 and 3)."),
        )

    def test_a_repeat_group_row_and_a_row_matched_by_email_instead_of_its_uuid(self):
        batch = self.stage_uuid_rows(
            [
                self.uuid_row(None, "ann@example.com", First_Name="Ann", Last_Name="Example"),
                self.uuid_row(None, "ANN@example.com", First_Name="Ann", Last_Name="Example"),
                self.uuid_row(UNKNOWN_UUID, "ann@example.com", First_Name="Ann", Last_Name="Example"),
            ]
        )
        self.assertEqual(
            [r.conflict for r in batch.rows.order_by("row_number")],
            ["duplicate_in_sheet", "duplicate_in_sheet", "uuid_not_found"],
        )
        self.choose(batch, {2: ("use_row", []), 4: ("ignore_uuid", [])})

        result = self.confirm(batch)

        sentence = (
            "Rows 2 and 4 would all create a new member with ann@example.com. Choose one of them and skip the others."
        )
        self.assertEqual((result.status, result.message), ("refused", sentence))
        self.assertEqual(self.problems(batch), [sentence])
        self.assertFalse(Member.objects.filter(first_name="Ann").exists())

        # Using the group's other row as well is a second mistake, with its own sentence.
        self.choose(batch, {3: ("use_row", [])})

        self.assertEqual(
            self.problems(batch),
            [
                "Rows 2, 3 and 4 would all create a new member with ann@example.com / ANN@example.com (the same "
                "address in different letter case). Choose one of them and skip the others.",
                "Rows 2 and 3 are the same person; use only one of them (rows 2 and 3).",
            ],
        )
