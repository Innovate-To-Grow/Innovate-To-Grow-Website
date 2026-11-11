"""Every row the member import skips says why, and names the member it is about.

The "Row 5" report ("no member has … as their primary email") gave no reason. These tests pin the reasons for the
update path, the create-only path and the creation of new members, without changing which rows match: a row still
reaches an existing member only through that member's primary email.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.matching import lookup_contact_emails, lookup_contact_phones
from apps.authn.services.members.import_.operations import bulk_update_members
from apps.authn.services.members.import_.parsing import parse_row
from apps.authn.services.members.import_.types import ImportMessage, ImportResult

from .import_sheets import FULL_HEADERS, build_sheet, full_row

HEADERS = ["Primary Email", "First Name", "Last Name", "Secondary Email", "Phone Number", "Organization"]


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
                "Row 5: no member has neil.parkhi@work.example as their primary email: it is the secondary email of "
                f"Neil Parkhi (member {self.neil.pk}), whose primary email is neil@home.example. Row not imported. "
                "Rows are matched to existing members by primary email only: put the member's primary email in the "
                "Primary Email cell, or make this address their primary email on the member page first"
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

        self.assertIn("it is the other email of Neil Parkhi", result.errors[0])

    def test_unlinked_address(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.com")

        result = import_members_from_excel(
            build_sheet(HEADERS, [["orphan@example.com", "Or", "Phan", None, None, None]]), update_existing=True
        )

        self.assertEqual(
            result.errors,
            [
                "Row 2: no member has orphan@example.com as their primary email: it is a contact email that is not "
                "linked to any member. Row not imported: link it to a member (or delete it) under Contact Emails first"
            ],
        )
        self.assertIsNone(result.errors[0].member_id)

    def test_case_only_duplicates_are_skipped_instead_of_picking_one(self):
        """The old lookup kept whichever primary it met; the row might update the wrong person."""
        grace = _member("Grace", "Hopper", None)
        ContactEmail.objects.create(member=grace, email_address="Shared@Example.com", email_type="primary")
        ContactEmail.objects.create(member=self.neil, email_address="shared@example.com", email_type="other")

        result = import_members_from_excel(
            build_sheet(HEADERS, [["shared@example.com", "Who", "Ever", None, None, "Changed"]]), update_existing=True
        )

        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertIn("shared@example.com matches 2 contact emails that differ only in letter case", result.errors[0])
        self.assertIn(f"Shared@Example.com is the primary email of Grace Hopper (member {grace.pk})", result.errors[0])
        self.assertIn("merge the duplicates under Contact Emails first", result.errors[0])
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
                f"Row 2: You do not have permission to update Neil Parkhi (member {self.neil.pk}) (only an I2G "
                "Master may change staff and superuser accounts)"
            ],
        )
        self.assertEqual(result.errors[0].member_id, str(self.neil.pk))

    def test_a_failing_row_is_rolled_back_and_named(self):
        sheet = build_sheet(HEADERS, [["neil@home.example", "Renamed", "Parkhi", None, "+12095550001", "Org"]])

        with patch("apps.authn.services.members.import_.operations.sync_phone", side_effect=RuntimeError("phone boom")):
            result = import_members_from_excel(sheet, update_existing=True)

        self.assertEqual((result.updated_count, result.skipped_count), (0, 1))
        self.assertEqual(
            result.errors,
            [
                f"Row 2: could not update Neil Parkhi (member {self.neil.pk}): phone boom. Nothing in this row was "
                "changed"
            ],
        )
        self.neil.refresh_from_db()
        self.assertEqual(self.neil.first_name, "Neil")


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
                f"Row 2: Member with email NEIL@home.example already exists: Neil Parkhi (member {self.neil.pk}). "
                'Skipped because "Update Existing Members" is off'
            ],
        )
        self.assertEqual(result.errors[0].member_id, str(self.neil.pk))

    def test_existing_secondary(self):
        ContactEmail.objects.create(member=self.neil, email_address="work@example.com", email_type="secondary")

        result = self._import("work@example.com")

        self.assertIn(
            f"work@example.com already exists: it is the secondary email of Neil Parkhi (member {self.neil.pk}), "
            "whose primary email is neil@home.example. Row not imported",
            result.errors[0],
        )

    def test_existing_unlinked(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.com")

        result = self._import("orphan@example.com")

        self.assertIn("orphan@example.com already exists: it is a contact email that is not linked", result.errors[0])

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

    def test_primary_already_used_as_an_earlier_rows_secondary(self):
        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["ada@example.com", "Ada", "Lovelace", "shared@example.com", None, None],
                    ["shared@example.com", "Grace", "Hopper", None, None, None],
                ],
            )
        )

        self.assertEqual((result.created_count, result.skipped_count), (1, 1))
        self.assertEqual(result.errors, ["Row 3: shared@example.com is already used by row 2 of this file"])

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
                "Row 3: Secondary Email shared@example.com is already used by row 2 of this file; not added",
                "Row 3: Phone Number +12095550001 is already used by row 2 of this file; not added",
            ],
        )

    def test_duplicate_row_names_the_row_that_is_imported(self):
        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["dup@example.com", "Ada", "Lovelace", None, None, None],
                    ["DUP@example.com", "Grace", "Hopper", None, None, None],
                ],
            )
        )

        self.assertEqual(
            result.errors,
            ["Row 3: Duplicate email in file (DUP@example.com): row 2 has it too, and only that row is imported"],
        )

    def test_a_new_members_own_flags_are_still_taken_from_the_sheet(self):
        result = import_members_from_excel(
            build_sheet(
                FULL_HEADERS,
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
                    )
                ],
            )
        )

        self.assertEqual((result.created_count, result.warnings), (1, []))
        primary = ContactEmail.objects.get(email_address="ada@example.com")
        self.assertEqual((primary.verified, primary.subscribe), (True, False))
        self.assertTrue(ContactEmail.objects.get(email_address="alt@example.com").verified)
        phone = ContactPhone.objects.get(phone_number="2095550001")
        self.assertEqual((phone.verified, phone.subscribe), (True, True))

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

        with patch(
            "apps.authn.services.members.import_.excel.Member.objects.bulk_create", side_effect=RuntimeError("db down")
        ):
            result = import_members_from_excel(sheet)

        self.assertFalse(result.success)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.errors, ["Error creating members: db down"])

    def test_messages_are_listed_in_row_order(self):
        neil = _member("Neil", "Parkhi", "neil@home.example")
        ContactEmail.objects.create(member=neil, email_address="neil@work.example", email_type="secondary")

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["neil@work.example", "Neil", "Parkhi", None, None, None],
                    ["ada@example.com", "Ada", "", None, None, None],
                    ["neil@home.example", "Neil", "Parkhi", None, None, None],
                    ["grace@example.com", "Grace", "Hopper", "grace at home", None, None],
                ],
            ),
            update_existing=True,
        )

        # Creation runs before the updates, so unsorted these would read rows 3, 2 and 5, 4.
        self.assertEqual([message.row for message in result.errors], [2, 3])
        self.assertEqual([message.row for message in result.warnings], [4, 5])
        self.assertIn("Row 4: Secondary Email is blank; kept neil@work.example", result.warnings[0])
        self.assertEqual(result.updated_count, 1)


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

    def test_phone_cell_without_national_digits_is_ignored(self):
        neil = _member("Neil", "Parkhi", "neil@home.example")

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["ada@example.com", "Ada", "Lovelace", None, "+1", None],
                    ["neil@home.example", "Neil", "Parkhi", None, "1", None],
                ],
            ),
            update_existing=True,
        )

        self.assertEqual((result.created_count, result.updated_count), (1, 1))
        self.assertFalse(ContactPhone.objects.exists())
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Phone Number +1 has no digits after the country code; ignored",
                "Row 3: Phone Number +1 has no digits after the country code; ignored",
            ],
        )
        self.assertEqual(result.warnings[1].member_id, str(neil.pk))

    def test_lookups_of_nothing_query_nothing(self):
        with self.assertNumQueries(0):
            self.assertEqual(lookup_contact_emails([None, ""]), {})
            self.assertEqual(lookup_contact_phones([None, ""]), {})

    def test_address_that_disappeared_before_the_update_is_skipped(self):
        """Routing saw the address, but it was deleted before the update phase ran."""
        result = ImportResult(success=True)

        bulk_update_members([parse_row(7, {"primary_email": "gone@example.com"})], result)

        self.assertEqual(
            result.errors,
            [
                "Row 7: no member has gone@example.com as their primary email: no contact email has this address any "
                "more. Row not imported"
            ],
        )
        self.assertEqual(result.skipped_count, 1)
