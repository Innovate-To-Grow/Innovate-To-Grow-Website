"""One row applied to one existing member: what the planner plans and the executor writes (``review/plan.py``)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.members.import_.review.actions import UPDATE, Action
from apps.authn.services.members.import_.review.execute import execute_update
from apps.authn.services.members.import_.review.lookup import load_snapshot
from apps.authn.services.members.import_.review.plan import STAFF_IGNORED, plan_row

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
        "primary_verified": None,
        "primary_subscribed": None,
        "secondary_email": None,
        "secondary_verified": False,
        "secondary_subscribed": False,
        "phone_number": None,
        "phone_subscribed": False,
        "phone_verified": False,
        "member_uuid": None,
        "notes": [],
    }
    base.update(overrides)
    return base


def update(member, parsed, ticks=()):
    """Plan ``parsed`` for ``member`` (as a confirmed "update" choice) and write it; return the plan."""
    snapshot = load_snapshot([{**parsed, "member_uuid": str(member.pk)}])
    plan = plan_row(parsed, Action(UPDATE, target=str(member.pk)), snapshot, ticks=ticks)
    execute_update(parsed["row"], plan, member)
    return plan


class UpdateOneMemberTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Old", last_name="Name", is_active=True
        )
        self.primary = ContactEmail.objects.create(
            member=self.member, email_address="user@example.com", email_type="primary", verified=False
        )

    def test_updates_all_optional_fields(self):
        parsed = _parsed(middle_name="Quincy", title="Engineer", organization="Acme", is_active=True, is_staff=True)

        plan = update(self.member, parsed, ticks=[f"R8:{self.member.pk}"])

        self.member.refresh_from_db()
        self.assertEqual(
            (self.member.first_name, self.member.middle_name, self.member.title, self.member.organization),
            ("New", "Quincy", "Engineer", "Acme"),
        )
        self.assertTrue(self.member.is_staff)
        self.assertEqual(plan.notes, [])
        self.assertIn("Grants staff status", plan.changes)

    def test_is_staff_is_ignored_without_its_tick(self):
        """The Staff column is an I2G Master field; the export/re-import round trip must not grant it."""
        plan = update(self.member, _parsed(is_staff=True))

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_staff)
        self.assertEqual(plan.notes, [STAFF_IGNORED])

    def test_unchanged_staff_column_is_not_reported(self):
        """An export carries Staff on every row; a value that changes nothing is not a note."""
        self.assertEqual(update(self.member, _parsed(is_staff=False)).notes, [])

    def test_only_the_changed_fields_are_written(self):
        """The instance is loaded before the rows run; a full save would undo an admin's change made meanwhile."""
        stale = Member.objects.get(pk=self.member.pk)
        Member.objects.filter(pk=self.member.pk).update(title="Set by an admin")
        parsed = _parsed(organization="Acme")
        snapshot = load_snapshot([{**parsed, "member_uuid": str(self.member.pk)}])
        Member.objects.filter(pk=self.member.pk).update(is_active=False)

        execute_update(2, plan_row(parsed, Action(UPDATE, target=str(self.member.pk)), snapshot), stale)

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.title, "Set by an admin")
        self.assertEqual(self.member.organization, "Acme")

    def test_a_row_that_changes_nothing_writes_nothing(self):
        before = Member.objects.get(pk=self.member.pk).updated_at

        plan = update(self.member, _parsed(first_name="Old", primary_verified=None, primary_subscribed=None))

        self.assertFalse(plan.writes)
        self.assertEqual(Member.objects.get(pk=self.member.pk).updated_at, before)

    def test_absent_flag_columns_preserve_the_stored_values(self):
        """A sheet without the verified/subscribed columns must not de-verify the primary email."""
        ContactEmail.objects.filter(pk=self.primary.pk).update(verified=True, subscribe=True)

        update(self.member, _parsed(primary_verified=None, primary_subscribed=None))

        self.primary.refresh_from_db()
        self.assertEqual((self.primary.verified, self.primary.subscribe), (True, True))

    def test_absent_phone_column_does_not_delete_stored_phones(self):
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US")

        plan = update(self.member, _parsed(phone_number=None))  # no has_phone_column key at all

        self.assertEqual(self.member.contact_phones.count(), 1)
        self.assertEqual(plan.notes, [])

    def test_blank_cell_in_a_present_phone_column_keeps_the_phone(self):
        """Used to hard-delete every phone (a phone-only member's only way to sign in)."""
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US", verified=True)

        plan = update(self.member, _parsed(phone_number=None, has_phone_column=True))

        phone = ContactPhone.objects.get(member=self.member)
        self.assertEqual((phone.phone_number, phone.verified), ("2095551234", True))
        self.assertEqual(len(plan.notes), 1)
        self.assertIn("Phone Number is blank; kept +12095551234", plan.notes[0])

    def test_absent_secondary_column_does_not_delete_secondary_emails(self):
        ContactEmail.objects.create(
            member=self.member, email_address="second@example.com", email_type="secondary", verified=True
        )

        update(self.member, _parsed(secondary_email=None))

        self.assertEqual(self.member.contact_emails.filter(email_type="secondary").count(), 1)

    def test_primary_flags_unsubscribe_freely_and_verify_only_with_their_tick(self):
        """FALSE unsubscribes (an opt-out); TRUE verifies only with the R9 tick (a verified address is a sign-in)."""
        unticked = update(self.member, _parsed(first_name="Old", primary_verified=True, primary_subscribed=False))
        self.primary.refresh_from_db()
        self.assertEqual((self.primary.verified, self.primary.subscribe), (False, False))
        self.assertIn(
            "Primary Verified is TRUE, but user@example.com is unverified; left unverified", unticked.notes[0]
        )

        plan = update(self.member, _parsed(first_name="Old", primary_verified=True), ticks=[f"R9:{self.primary.pk}"])

        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)
        self.assertEqual(plan.notes, [])
        self.assertEqual(plan.changes, ["Marks user@example.com verified"])

    def test_primary_email_is_never_created_for_a_member_without_it(self):
        """A row matched by Member UUID never adds or re-types an address from its Primary Email cell."""
        bare = Member.objects.create_user(password="StrongPass123!", first_name="No", last_name="Email")

        plan = update(bare, _parsed(primary_email="fresh@example.com", first_name="No", last_name="Email"))

        self.assertFalse(ContactEmail.objects.filter(email_address="fresh@example.com").exists())
        self.assertFalse(ContactEmail.objects.filter(member=bare).exists())
        self.assertIn("Primary Email fresh@example.com is not one of the member's addresses", plan.notes[0])

    def test_existing_other_email_named_as_secondary_keeps_its_role(self):
        """The Secondary cells' flags apply (safe direction) to the address the member owns; its role is kept."""
        ContactEmail.objects.create(
            member=self.member, email_address="sec@example.com", email_type="other", verified=False
        )

        sec = ContactEmail.objects.get(member=self.member, email_address="sec@example.com")
        plan = update(
            self.member, _parsed(secondary_email="sec@example.com", secondary_verified=True), ticks=[f"R9:{sec.pk}"]
        )

        sec.refresh_from_db()
        self.assertEqual((sec.email_type, sec.verified), ("other", True))
        self.assertEqual(
            plan.notes, ['Secondary Email sec@example.com is already this member\'s "other" email; left as it is']
        )

    def test_new_phone_is_added_next_to_the_existing_one(self):
        """Used to overwrite the first phone in place, keeping its "verified" flag for the new number."""
        old = ContactPhone.objects.create(member=self.member, phone_number="2095550000", region="1-US", verified=True)

        plan = update(self.member, _parsed(phone_number="+12095559999"))

        old.refresh_from_db()
        self.assertEqual((old.phone_number, old.verified), ("2095550000", True))
        self.assertFalse(ContactPhone.objects.get(member=self.member, phone_number="2095559999").verified)
        self.assertIn(
            "Adds phone +12095559999 (unverified, not subscribed); keeps +12095550000 (an import never replaces a "
            "number in place)",
            plan.changes,
        )
