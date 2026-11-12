"""Every row the import without a review skips says why, and names the member it is about.

``import_members_from_excel`` runs the review's analysis and applies what a review would apply untouched: every row
that needs a decision (C1–C9) is skipped with its reason, and nothing risky is done. These tests pin the reasons, the
notes on imported rows, and that the whole import is one transaction.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.parsing import PHONE_VERIFIED_IGNORED
from apps.authn.services.members.import_.review.lookup import load_snapshot
from apps.authn.services.members.import_.types import ImportMessage

from .import_sheets import FULL_HEADERS, PHONE_VERIFIED_HEADERS, build_sheet, full_row

HEADERS = ["Primary Email", "First Name", "Last Name", "Secondary Email", "Phone Number", "Organization"]
C7 = "needs a decision (C7: The address is a member's secondary or other email)"


def _member(first, last, primary, **primary_flags):
    member = Member.objects.create_user(password="StrongPass123!", first_name=first, last_name=last, is_active=True)
    if primary:
        ContactEmail.objects.create(member=member, email_address=primary, email_type="primary", **primary_flags)
    return member


class UpdateModeSkipReasonTests(TestCase):
    def setUp(self):
        cache.clear()
        self.neil = _member("Neil", "Parkhi", "neil@home.example", verified=True)
        self.work = ContactEmail.objects.create(
            member=self.neil, email_address="neil.parkhi@work.example", email_type="secondary", verified=True
        )

    def _rows(self, row5):
        """Three new members on rows 2-4, then the row under test on row 5."""
        filler = [[f"new{i}@example.com", "New", f"Person{i}", None, None, None] for i in range(3)]
        return build_sheet(HEADERS, [*filler, row5])

    def test_row5_secondary_address_says_whose_it_is_and_changes_nothing(self):
        result = import_members_from_excel(
            self._rows(["neil.parkhi@work.example", "Neil", "Parkhi", None, None, "Spirit"]), update_existing=True
        )

        self.assertEqual((result.created_count, result.updated_count, result.skipped_count), (3, 0, 1))
        self.assertEqual(
            result.errors,
            [
                f"Row 5: {C7}. neil.parkhi@work.example is the secondary email of Neil Parkhi (member {self.neil.pk}), "
                "whose primary email is neil@home.example."
            ],
        )
        message = result.errors[0]
        self.assertIsInstance(message, ImportMessage)
        self.assertEqual((message.row, message.member_id), (5, str(self.neil.pk)))
        # Nothing about Neil changed: in particular the blank Secondary cell did not delete the matched address.
        self.work.refresh_from_db()
        self.assertEqual((self.work.member, self.work.email_type, self.work.verified), (self.neil, "secondary", True))
        self.neil.refresh_from_db()
        self.assertIsNone(self.neil.organization)

    def test_other_address(self):
        ContactEmail.objects.filter(pk=self.work.pk).update(email_type="other")

        result = import_members_from_excel(
            build_sheet(HEADERS, [["neil.parkhi@work.example", "Neil", "Parkhi", None, None, None]]),
            update_existing=True,
        )

        self.assertIn("is the other email of Neil Parkhi", result.errors[0])

    def test_unlinked_address(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.com")

        result = import_members_from_excel(
            build_sheet(HEADERS, [["orphan@example.com", "Or", "Phan", None, None, None]]), update_existing=True
        )

        self.assertEqual(len(result.errors), 1)
        self.assertIn(
            "Row 2: needs a decision (C8: The address exists, but with no member). orphan@example.com is a contact "
            "email with no member (added ",
            result.errors[0],
        )
        self.assertIsNone(result.errors[0].member_id)
        self.assertIsNone(ContactEmail.objects.get(email_address="orphan@example.com").member)

    def test_case_only_duplicates_are_skipped_instead_of_picking_one(self):
        """The old lookup kept whichever primary it met; the row might update the wrong person."""
        grace = _member("Grace", "Hopper", None)
        ContactEmail.objects.create(member=grace, email_address="Shared@Example.com", email_type="primary")
        ContactEmail.objects.create(member=self.neil, email_address="shared@example.com", email_type="other")

        result = import_members_from_excel(
            build_sheet(HEADERS, [["shared@example.com", "Who", "Ever", None, None, "Changed"]]), update_existing=True
        )

        self.assertEqual((result.updated_count, result.skipped_count), (0, 1))
        self.assertIn("(C3: The address exists more than once, differing only in letter case)", result.errors[0])
        self.assertIn("shared@example.com matches 2 contact emails that differ only in letter case", result.errors[0])
        self.assertIn(f"Shared@Example.com is the primary email of Grace Hopper (member {grace.pk})", result.errors[0])
        self.assertIn("Merge the duplicates under Contact Emails", result.errors[0])
        grace.refresh_from_db()
        self.assertNotEqual(grace.organization, "Changed")

    def test_permission_refusal_names_the_member(self):
        result = import_members_from_excel(
            build_sheet(HEADERS, [["neil@home.example", "Neil", "Parkhi", None, None, "Org"]]),
            update_existing=True,
            update_member_allowed=lambda member: False,
        )

        self.assertEqual(
            result.errors,
            [
                "Row 2: needs a decision (C2: A staff or superuser account). You do not have permission to update "
                f"Neil Parkhi (member {self.neil.pk}) (only an I2G Master may change staff and superuser accounts)."
            ],
        )
        self.assertEqual(result.errors[0].member_id, str(self.neil.pk))

    def test_a_failing_row_rolls_back_the_whole_import(self):
        sheet = self._rows(["neil@home.example", "Neil", "Parkhi", None, "+12095550001", "Org"])

        with patch(
            "apps.authn.services.members.import_.contacts.create_contact_phone", side_effect=RuntimeError("phone boom")
        ):
            result = import_members_from_excel(sheet, update_existing=True)

        self.assertFalse(result.success)
        self.assertEqual((result.created_count, result.updated_count), (0, 0))
        self.assertEqual(result.errors, ["Error importing members: Row 5: phone boom. Nothing was imported"])
        self.assertFalse(Member.objects.filter(first_name="New").exists())
        self.neil.refresh_from_db()
        self.assertIsNone(self.neil.organization)


class CreateOnlySkipReasonTests(TestCase):
    def setUp(self):
        cache.clear()
        self.neil = _member("Neil", "Parkhi", "neil@home.example")

    def _import(self, address):
        return import_members_from_excel(build_sheet(HEADERS, [[address, "Neil", "Parkhi", None, None, None]]))

    def test_existing_primary(self):
        result = self._import("NEIL@home.example")

        self.assertEqual(
            result.errors,
            [
                "Row 2: needs a decision (C9: Matches an existing member, and the upload said to skip those). "
                f"NEIL@home.example is the primary email of Neil Parkhi (member {self.neil.pk}), and the upload said "
                "to skip rows that match an existing member."
            ],
        )
        self.assertEqual(result.errors[0].member_id, str(self.neil.pk))

    def test_existing_secondary(self):
        ContactEmail.objects.create(member=self.neil, email_address="work@example.com", email_type="secondary")

        result = self._import("work@example.com")

        self.assertIn(
            f"{C7}. work@example.com is the secondary email of Neil Parkhi (member {self.neil.pk}), whose primary "
            "email is neil@home.example.",
            result.errors[0],
        )

    def test_existing_unlinked(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.com")

        result = self._import("orphan@example.com")

        self.assertIn("orphan@example.com is a contact email with no member", result.errors[0])

    def test_existing_case_only_duplicates(self):
        ContactEmail.objects.create(member=None, email_address="Twin@example.com")
        ContactEmail.objects.create(member=None, email_address="twin@example.com")

        result = self._import("twin@example.com")

        self.assertIn("twin@example.com matches 2 contact emails that differ only in letter case", result.errors[0])


class NewMemberMessageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_invalid_primary_email_is_not_created(self):
        result = import_members_from_excel(
            build_sheet(HEADERS, [["not-an-email", "Ada", "Lovelace", None, None, None]])
        )

        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.errors, ["Row 2: Primary Email 'not-an-email' is not a valid email address"])
        self.assertFalse(Member.objects.filter(first_name="Ada").exists())

    def test_invalid_secondary_is_dropped_with_a_note(self):
        result = import_members_from_excel(
            build_sheet(HEADERS, [["ada@example.com", "Ada", "Lovelace", "ada at home", None, None]])
        )

        self.assertEqual(result.created_count, 1)
        self.assertEqual(ContactEmail.objects.filter(email_address__startswith="ada").count(), 1)
        self.assertEqual(
            result.warnings, ["Row 2: Secondary Email 'ada at home' is not a valid email address; ignored"]
        )

    def test_secondary_and_phone_held_by_another_member_are_reported(self):
        grace = _member("Grace", "Hopper", "grace@example.com")
        ContactEmail.objects.create(member=grace, email_address="shared@example.com", email_type="secondary")
        ContactPhone.objects.create(member=grace, phone_number="2095550001", region="1-US")

        result = import_members_from_excel(
            build_sheet(HEADERS, [["ada@example.com", "Ada", "Lovelace", "shared@example.com", "+12095550001", None]])
        )

        self.assertEqual(result.created_count, 1)
        self.assertEqual(
            result.warnings,
            [
                f"Row 2: Secondary Email shared@example.com is already used by Grace Hopper (member {grace.pk}); "
                "not added",
                f"Row 2: Phone Number +12095550001 is already used by Grace Hopper (member {grace.pk}); not added",
            ],
        )
        self.assertEqual(ContactEmail.objects.get(email_address="shared@example.com").member, grace)
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550001").member, grace)

    def test_secondary_equal_to_primary_is_reported(self):
        result = import_members_from_excel(
            build_sheet(HEADERS, [["ada@example.com", "Ada", "Lovelace", "Ada@Example.com", None, None]])
        )

        self.assertEqual(ContactEmail.objects.count(), 1)
        self.assertEqual(result.warnings, ["Row 2: Secondary Email is the same as the Primary Email; ignored"])

    def test_one_rows_primary_wins_over_another_rows_secondary(self):
        """V8: the address is created as row 3's primary; row 2's Secondary cell is set aside."""
        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["ada@example.com", "Ada", "Lovelace", "shared@example.com", None, None],
                    ["shared@example.com", "Grace", "Hopper", None, None, None],
                ],
            )
        )

        self.assertEqual((result.created_count, result.skipped_count), (2, 0))
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Secondary Email shared@example.com is the Primary Email of row 3; that row wins, and this cell is ignored"
            ],
        )
        shared = ContactEmail.objects.get(email_address="shared@example.com")
        self.assertEqual((shared.member.first_name, shared.email_type), ("Grace", "primary"))

    def test_secondary_and_phone_already_used_by_an_earlier_row(self):
        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["ada@example.com", "Ada", "Lovelace", "shared@example.com", "+12095550001", None],
                    ["grace@example.com", "Grace", "Hopper", "shared@example.com", "+12095550001", None],
                ],
            )
        )

        self.assertEqual(result.created_count, 2)
        self.assertEqual(
            result.warnings,
            [
                "Row 3: Secondary Email shared@example.com is also in row 2; only that row adds it",
                "Row 3: Phone Number +12095550001 is also in row 2; only that row adds it",
            ],
        )

    def test_repeated_rows_are_all_skipped_until_someone_picks_one(self):
        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["dup@example.com", "Ada", "Lovelace", None, None, None],
                    ["DUP@example.com", "Grace", "Hopper", None, None, None],
                ],
            )
        )

        self.assertEqual((result.created_count, result.skipped_count), (0, 2))
        prefix = "needs a decision (C1: The same person appears more than once in the sheet). Rows 2, 3 all resolve to"
        self.assertEqual([message.row for message in result.errors], [2, 3])
        self.assertTrue(all(prefix in message for message in result.errors))

    def test_a_new_members_own_email_flags_are_still_taken_from_the_sheet_but_never_phone_verified(self):
        result = import_members_from_excel(
            build_sheet(
                PHONE_VERIFIED_HEADERS,
                [
                    full_row(
                        "ada@example.com",
                        {
                            "Primary Verified": "TRUE",
                            "Primary Subscribed": "FALSE",
                            "Secondary Email": "alt@example.com",
                            "Secondary Verified": "TRUE",
                            "Phone Number": "+12095550001",
                            "Phone Subscribed": "TRUE",
                            "Phone Verified": "TRUE",
                        },
                        headers=PHONE_VERIFIED_HEADERS,
                    )
                ],
            )
        )

        self.assertEqual((result.created_count, result.warnings), (1, [PHONE_VERIFIED_IGNORED]))
        primary = ContactEmail.objects.get(email_address="ada@example.com")
        self.assertEqual((primary.verified, primary.subscribe), (True, False))
        self.assertTrue(ContactEmail.objects.get(email_address="alt@example.com").verified)
        phone = ContactPhone.objects.get(phone_number="2095550001")
        self.assertEqual((phone.verified, phone.subscribe), (False, True))

    def test_unrecognised_flag_text_on_a_new_member_is_reported(self):
        result = import_members_from_excel(
            build_sheet(FULL_HEADERS, [full_row("ada@example.com", {"Primary Subscribed": "maybe"})])
        )

        self.assertTrue(ContactEmail.objects.get(email_address="ada@example.com").subscribe)
        self.assertEqual(
            result.warnings, ["Row 2: Primary Subscribed cell 'maybe' is not TRUE or FALSE; it was ignored"]
        )

    def test_notes_of_a_failed_creation_are_dropped(self):
        sheet = build_sheet(HEADERS, [["ada@example.com", "Ada", "Lovelace", "bad address", None, None]])

        with patch("apps.authn.models.Member.objects.bulk_create", side_effect=RuntimeError("db down")):
            result = import_members_from_excel(sheet)

        self.assertFalse(result.success)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.errors, ["Error importing members: db down. Nothing was imported"])

    def test_messages_are_listed_in_row_order(self):
        neil = _member("Neil", "Parkhi", "neil@home.example")
        ContactEmail.objects.create(member=neil, email_address="neil@work.example", email_type="secondary")

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["neil@work.example", "Neil", "Parkhi", None, None, None],
                    ["ada@example.com", "Ada", "", None, None, None],
                    ["neil@home.example", "Neil", "Parkhi", None, None, "Org"],
                    ["grace@example.com", "Grace", "Hopper", "grace at home", None, None],
                ],
            ),
            update_existing=True,
        )

        # Rows 2 and 4 are both Neil (C1), row 3 has no last name; only row 5 is created.
        self.assertEqual([message.row for message in result.errors], [2, 3, 4])
        self.assertEqual([message.row for message in result.warnings], [5])
        self.assertEqual((result.created_count, result.updated_count), (1, 0))


class EdgeCaseTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_over_long_addresses_are_refused_before_they_reach_the_database(self):
        """PostgreSQL rejects an address over the column limit, which would roll back every creation."""
        long_address = f"{'a' * 250}@example.com"

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    [long_address, "Ada", "Lovelace", None, None, None],
                    ["grace@example.com", "Grace", "Hopper", long_address, None, None],
                ],
            )
        )

        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.errors, [f"Row 2: Primary Email {long_address!r} is not a valid email address"])
        self.assertEqual(
            result.warnings, [f"Row 3: Secondary Email {long_address!r} is not a valid email address; ignored"]
        )

    def test_phone_cell_that_is_not_a_us_number_is_ignored(self):
        neil = _member("Neil", "Parkhi", "neil@home.example")

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["ada@example.com", "Ada", "Lovelace", None, "+1", None],
                    ["neil@home.example", "Neil", "Parkhi", None, "+44 20 7946 0958", None],
                ],
            ),
            update_existing=True,
        )

        self.assertEqual((result.created_count, result.updated_count, result.unchanged_count), (1, 1, 1))
        self.assertFalse(ContactPhone.objects.exists())
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Phone Number +1 is not a 10-digit US number; ignored",
                "Row 3: Phone Number +442079460958 is not a 10-digit US number; ignored",
            ],
        )
        self.assertEqual(result.warnings[1].member_id, str(neil.pk))

    def test_lookups_of_nothing_query_nothing(self):
        with self.assertNumQueries(0):
            snapshot = load_snapshot([{"primary_email": None, "secondary_email": "", "phone_number": None}])
        self.assertEqual((snapshot.emails, snapshot.phones, snapshot.members), ({}, {}, {}))
