"""The one-step member import never destroys data.

Regression tests for the silent data-loss paths of "Update Existing Members": blank cells deleting every secondary
email or phone, a named secondary deleting the others, a new phone overwriting the old one (and inheriting
"verified"), the flag cells re-subscribing or un-verifying, and the Active column flipping members.
"""

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_ import import_members_from_excel

from ..import_sheets import FULL_HEADERS, build_sheet, full_row


class _ImportCase(TestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Ada", last_name="Lovelace", is_active=True
        )
        self.primary = ContactEmail.objects.create(
            member=self.member, email_address="ada@example.com", email_type="primary", verified=True, subscribe=True
        )

    def _email(self, address, email_type="secondary", member=None, **flags):
        return ContactEmail.objects.create(
            member=self.member if member is None else member, email_address=address, email_type=email_type, **flags
        )

    def _phone(self, number, member=None, **flags):
        return ContactPhone.objects.create(
            member=self.member if member is None else member, phone_number=number, region="1-US", **flags
        )

    def _update(self, cells=None, headers=None, primary="ada@example.com"):
        if headers is None:
            sheet = build_sheet(FULL_HEADERS, [full_row(primary, cells)])
        else:
            sheet = build_sheet(headers, [cells])
        return import_members_from_excel(sheet, update_existing=True)

    def _other_member(self, first="Grace", last="Hopper", email="grace@example.com"):
        other = Member.objects.create_user(password="StrongPass123!", first_name=first, last_name=last)
        self._email(email, email_type="primary", member=other, verified=True)
        return other


class SecondaryEmailIsNeverDeletedTests(_ImportCase):
    def test_blank_secondary_cell_keeps_every_secondary(self):
        self._email("one@example.com", verified=True)
        self._email("two@example.com")

        result = self._update()

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(
            set(self.member.contact_emails.filter(email_type="secondary").values_list("email_address", flat=True)),
            {"one@example.com", "two@example.com"},
        )
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Row 2: Secondary Email is blank; kept", result.warnings[0])
        self.assertIn("one@example.com", result.warnings[0])
        self.assertIn("two@example.com", result.warnings[0])
        self.assertEqual(result.warnings[0].member_id, str(self.member.pk))

    def test_missing_secondary_column_keeps_secondaries_without_a_note(self):
        self._email("one@example.com")

        result = self._update(
            ["ada@example.com", "Ada", "Lovelace"], headers=["Primary Email", "First Name", "Last Name"]
        )

        self.assertTrue(self.member.contact_emails.filter(email_address="one@example.com").exists())
        self.assertEqual(result.warnings, [])

    def test_naming_one_secondary_keeps_the_others(self):
        """Export -> re-import wrote one secondary and used to delete the member's others."""
        self._email("one@example.com", verified=True)
        self._email("two@example.com")

        result = self._update({"Secondary Email": "two@example.com"})

        self.assertEqual(
            set(self.member.contact_emails.filter(email_type="secondary").values_list("email_address", flat=True)),
            {"one@example.com", "two@example.com"},
        )
        self.assertEqual(result.warnings, [])

    def test_new_secondary_is_added_and_the_previous_one_becomes_other(self):
        old = self._email("old@example.com", verified=True)

        result = self._update({"Secondary Email": "new@example.com"})

        old.refresh_from_db()
        self.assertEqual(old.email_type, "other")
        self.assertTrue(old.verified)
        new = ContactEmail.objects.get(email_address="new@example.com")
        self.assertEqual(
            (new.member, new.email_type, new.verified, new.subscribe), (self.member, "secondary", False, True)
        )
        self.assertEqual(result.warnings, [])
        self.assertEqual(
            result.details[0]["changes"],
            [
                "Adds new@example.com as the secondary email (unverified, subscribed); the previous secondary "
                'old@example.com becomes "other"'
            ],
        )

    def test_new_secondary_starts_unverified_whatever_the_sheet_says(self):
        result = self._update({"Secondary Email": "new@example.com", "Secondary Verified": "TRUE"})

        self.assertFalse(ContactEmail.objects.get(email_address="new@example.com").verified)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("new@example.com is added unverified", result.warnings[0])

    def test_secondary_owned_by_another_member_is_never_moved(self):
        other = self._other_member()
        theirs = self._email("shared@example.com", member=other, verified=True)
        mine = self._email("mine@example.com")

        result = self._update({"Secondary Email": "shared@example.com"})

        theirs.refresh_from_db()
        mine.refresh_from_db()
        self.assertEqual((theirs.member, theirs.email_type), (other, "secondary"))
        self.assertEqual((mine.member, mine.email_type), (self.member, "secondary"))
        self.assertEqual(
            result.warnings,
            [
                f"Row 2: Secondary Email shared@example.com belongs to Grace Hopper (member {other.pk}); not added "
                "(an import never moves a contact from one member to another)"
            ],
        )

    def test_unlinked_secondary_is_attached_unverified(self):
        """A contact email with no member loses nothing by being attached; it starts unverified (plan §4.2)."""
        unlinked = ContactEmail.objects.create(member=None, email_address="loose@example.com", verified=True)

        result = self._update({"Secondary Email": "loose@example.com", "Secondary Verified": "TRUE"})

        unlinked.refresh_from_db()
        self.assertEqual((unlinked.member, unlinked.email_type, unlinked.verified), (self.member, "secondary", False))
        self.assertIn("Attaches loose@example.com (a contact email with no member)", result.details[0]["changes"][0])
        self.assertIn("loose@example.com is added unverified", result.warnings[0])

    def test_secondary_equal_to_the_primary_is_ignored(self):
        self._email("one@example.com")

        result = self._update({"Secondary Email": "ADA@example.com"})

        self.assertTrue(self.member.contact_emails.filter(email_address="one@example.com").exists())
        self.assertEqual(result.warnings, ["Row 2: Secondary Email is the same as the Primary Email; ignored"])

    def test_invalid_secondary_is_ignored(self):
        result = self._update({"Secondary Email": "not an email"})

        self.assertFalse(ContactEmail.objects.filter(email_address="not an email").exists())
        self.assertEqual(
            result.warnings, ["Row 2: Secondary Email 'not an email' is not a valid email address; ignored"]
        )

    def test_secondary_matching_case_only_duplicates_is_not_added(self):
        other = self._other_member()
        self._email("Twin@example.com", member=other)
        self._email("twin@example.com", email_type="other", member=other)

        result = self._update({"Secondary Email": "TWIN@example.com"})

        self.assertFalse(self.member.contact_emails.filter(email_address__iexact="twin@example.com").exists())
        self.assertIn("matches 2 contact emails that differ only in letter case; not added", result.warnings[0])
