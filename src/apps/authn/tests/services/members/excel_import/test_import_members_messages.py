"""Every row the import without a review skips says why, and names the member it is about.

``import_members_from_excel`` runs the review's analysis and applies what a review would apply untouched: every row
that needs a decision (C1–C9) is skipped with its reason, and nothing risky is done. These tests pin the reasons, the
notes on imported rows, and that the whole import is one transaction.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.types import ImportMessage

from ..import_sheets import build_sheet

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
