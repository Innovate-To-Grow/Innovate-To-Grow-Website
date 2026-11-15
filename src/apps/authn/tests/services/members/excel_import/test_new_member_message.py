from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.parsing import PHONE_VERIFIED_IGNORED
from apps.authn.tests.services.members.excel_import.test_import_members_messages import HEADERS, _member

from ..import_sheets import FULL_HEADERS, PHONE_VERIFIED_HEADERS, build_sheet, full_row


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
                "Row 3: Secondary Email shared@example.com is also in row 2; only that row can add it; if that row is skipped, no row adds it",
                "Row 3: Phone Number +12095550001 is also in row 2; only that row can add it; if that row is skipped, no row adds it",
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
