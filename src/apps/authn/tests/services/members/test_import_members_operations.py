"""Direct coverage for import_.operations.update_single_member: one row applied to one existing member."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.members.import_.operations import STAFF_COLUMN_IGNORED, update_single_member

Member = get_user_model()


def _parsed(**overrides):
    base = {
        "row": 2,
        "primary_email": "user@example.com",
        "first_name": "New",
        "last_name": "Name",
        "middle_name": "",
        "title": "",
        "organization": "",
        "is_active": None,
        "is_staff": None,
        "date_joined": None,
        "primary_verified": True,
        "primary_subscribed": True,
        "secondary_email": None,
        "secondary_verified": False,
        "secondary_subscribed": False,
        "phone_number": None,
        "phone_subscribed": False,
        "phone_verified": False,
        "notes": [],
    }
    base.update(overrides)
    return base


class UpdateSingleMemberTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Old", last_name="Name", is_active=True
        )
        self.primary = ContactEmail.objects.create(
            member=self.member, email_address="user@example.com", email_type="primary", verified=False
        )

    def test_updates_all_optional_fields(self):
        # Exercises the middle_name/title/organization/is_active/is_staff branches.
        parsed = _parsed(
            middle_name="Quincy",
            title="Engineer",
            organization="Acme",
            is_active=True,
            is_staff=True,
        )
        notes = update_single_member(self.member, parsed, allow_privilege_fields=True)
        self.member.refresh_from_db()
        self.assertEqual(self.member.middle_name, "Quincy")
        self.assertEqual(self.member.title, "Engineer")
        self.assertEqual(self.member.organization, "Acme")
        self.assertTrue(self.member.is_staff)
        self.assertEqual(notes, [])

    def test_is_staff_is_ignored_without_the_privilege_flag(self):
        """The Staff column is an I2G Master field; the export/re-import round trip must not grant it."""
        parsed = _parsed(is_staff=True)

        notes = update_single_member(self.member, parsed)

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_staff)
        self.assertEqual(notes, [STAFF_COLUMN_IGNORED])

    def test_unchanged_staff_column_is_not_reported(self):
        """An export carries Staff on every row; a value that changes nothing is not a note."""
        notes = update_single_member(self.member, _parsed(is_staff=False))

        self.assertEqual(notes, [])

    def test_only_the_changed_fields_are_written(self):
        """The instance is loaded before the rows run; a full save would undo an admin's change made meanwhile."""
        stale = Member.objects.get(pk=self.member.pk)
        Member.objects.filter(pk=self.member.pk).update(is_active=False, title="Set by an admin")

        update_single_member(stale, _parsed(organization="Acme"))

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.title, "Set by an admin")
        self.assertEqual(self.member.organization, "Acme")

    def test_a_row_that_changes_nothing_writes_nothing(self):
        before = Member.objects.get(pk=self.member.pk).updated_at

        update_single_member(self.member, _parsed(first_name="Old", primary_verified=None, primary_subscribed=None))

        self.assertEqual(Member.objects.get(pk=self.member.pk).updated_at, before)

    def test_absent_flag_columns_preserve_the_stored_values(self):
        """A sheet without the verified/subscribed columns must not de-verify the primary email."""
        self.primary.verified = True
        self.primary.subscribe = True
        self.primary.save(update_fields=["verified", "subscribe"])
        parsed = _parsed(primary_verified=None, primary_subscribed=None)

        update_single_member(self.member, parsed)

        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)
        self.assertTrue(self.primary.subscribe)

    def test_absent_phone_column_does_not_delete_stored_phones(self):
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US")
        parsed = _parsed(phone_number=None)  # no has_phone_column key at all

        notes = update_single_member(self.member, parsed)

        self.assertEqual(self.member.contact_phones.count(), 1)
        self.assertEqual(notes, [])

    def test_blank_cell_in_a_present_phone_column_keeps_the_phone(self):
        """Used to hard-delete every phone (a phone-only member's only way to sign in)."""
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US", verified=True)
        parsed = _parsed(phone_number=None, has_phone_column=True)

        notes = update_single_member(self.member, parsed)

        phone = ContactPhone.objects.get(member=self.member)
        self.assertEqual(phone.phone_number, "2095551234")
        self.assertTrue(phone.verified)
        self.assertEqual(len(notes), 1)
        self.assertIn("Phone Number is blank; kept +12095551234", notes[0])

    def test_absent_secondary_column_does_not_delete_secondary_emails(self):
        ContactEmail.objects.create(
            member=self.member, email_address="second@example.com", email_type="secondary", verified=True
        )
        parsed = _parsed(secondary_email=None)

        update_single_member(self.member, parsed)

        self.assertEqual(self.member.contact_emails.filter(email_type="secondary").count(), 1)

    def test_primary_flags_apply_in_the_safe_direction(self):
        """TRUE verifies (as "Mark verified" does) and FALSE unsubscribes (an opt-out)."""
        parsed = _parsed(primary_verified=True, primary_subscribed=False)

        notes = update_single_member(self.member, parsed)

        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)
        self.assertFalse(self.primary.subscribe)
        self.assertEqual(notes, [])

    def test_primary_email_is_never_created_for_a_member_without_it(self):
        """The import matched the member by this address; it never creates or re-types a primary email."""
        bare = Member.objects.create_user(password="StrongPass123!", first_name="No", last_name="Email")
        parsed = _parsed(primary_email="fresh@example.com")

        update_single_member(bare, parsed)

        self.assertFalse(ContactEmail.objects.filter(email_address="fresh@example.com").exists())
        self.assertFalse(ContactEmail.objects.filter(member=bare).exists())

    def test_existing_other_email_named_as_secondary_is_left_alone(self):
        """Roles and flags of an address the member already has are not changed by the Secondary cells."""
        ContactEmail.objects.create(
            member=self.member, email_address="sec@example.com", email_type="other", verified=False
        )
        parsed = _parsed(secondary_email="sec@example.com", secondary_verified=True)

        notes = update_single_member(self.member, parsed)

        sec = ContactEmail.objects.get(member=self.member, email_address="sec@example.com")
        self.assertEqual(sec.email_type, "other")
        self.assertFalse(sec.verified)
        self.assertEqual(
            notes, ['Secondary Email sec@example.com is already this member\'s "other" email; left as it is']
        )

    def test_new_phone_is_added_next_to_the_existing_one(self):
        """Used to overwrite the first phone in place, keeping its "verified" flag for the new number."""
        old = ContactPhone.objects.create(member=self.member, phone_number="2095550000", region="1-US", verified=True)
        parsed = _parsed(phone_number="+12095559999")

        notes = update_single_member(self.member, parsed)

        old.refresh_from_db()
        self.assertEqual(old.phone_number, "2095550000")
        self.assertTrue(old.verified)
        new = ContactPhone.objects.get(member=self.member, phone_number="2095559999")
        self.assertFalse(new.verified)
        self.assertEqual(
            notes,
            ["Added +12095559999 as an additional phone number; kept +12095550000 (an import never replaces a number)"],
        )
