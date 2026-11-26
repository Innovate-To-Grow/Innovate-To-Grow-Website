from unittest.mock import patch

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.tests.services.members.excel_import.test_import_members_excel import _ImportMembersExcelCase


class ImportMembersExcelTests(_ImportMembersExcelCase):
    def test_creates_member_with_emails_and_phone(self):
        workbook = self._build_full_workbook(
            [
                ["main@example.com", "Ada", "Lovelace", "alt@example.com", "+12095551234", "Acme"],
            ]
        )
        result = import_members_from_excel(workbook)
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 1)
        self.assertTrue(ContactEmail.objects.filter(email_address="main@example.com").exists())
        self.assertTrue(ContactEmail.objects.filter(email_address="alt@example.com").exists())
        self.assertTrue(ContactPhone.objects.filter(phone_number="2095551234").exists())

    def test_exception_during_create_sets_failure(self):
        workbook = self._build_workbook([["boom@example.com", "Ada", "Lovelace", "Acme"]])
        with patch(
            "apps.authn.models.Member.objects.bulk_create",
            side_effect=RuntimeError("db blew up"),
        ):
            result = import_members_from_excel(workbook)
        self.assertFalse(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.errors, ["Error importing members: db blew up. Nothing was imported"])

    def test_update_existing_updates_contacts_and_phone(self):
        member = Member.objects.create_user(password="StrongPass123!", first_name="Old", last_name="Name")
        ContactEmail.objects.create(
            member=member, email_address="upd@example.com", email_type="primary", verified=False, subscribe=False
        )
        workbook = self._build_full_workbook(
            [
                ["upd@example.com", "Old", "Name", "second@example.com", "+12095559999", "NewOrg"],
            ]
        )
        result = import_members_from_excel(workbook, update_existing=True)
        member.refresh_from_db()
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(member.first_name, "Old")
        self.assertEqual(member.organization, "NewOrg")
        self.assertTrue(ContactEmail.objects.filter(member=member, email_type="secondary").exists())
        self.assertTrue(ContactPhone.objects.filter(member=member, phone_number="2095559999").exists())

    def test_update_existing_updates_an_admin_like_any_member_and_never_its_admin_access(self):
        member = Member.objects.create_user(
            password="StrongPass123!", first_name="Old", last_name="Name", is_staff=True
        )
        ContactEmail.objects.create(
            member=member, email_address="admin@example.com", email_type="primary", verified=True
        )
        workbook = self._build_full_workbook([["admin@example.com", "Old", "Name", None, None, "NewOrg"]])

        result = import_members_from_excel(workbook, update_existing=True)

        member.refresh_from_db()
        self.assertEqual((result.updated_count, result.skipped_count, result.errors), (1, 0, []))
        self.assertEqual(member.organization, "NewOrg")
        self.assertEqual((member.is_staff, member.is_superuser, member.is_active), (True, True, True))

    def test_update_existing_keeps_the_secondary_and_adds_the_new_phone(self):
        # A blank Secondary cell and a different phone used to delete the secondary and overwrite the phone.
        member = Member.objects.create_user(password="StrongPass123!", first_name="Old", last_name="Name")
        ContactEmail.objects.create(
            member=member, email_address="repl@example.com", email_type="primary", verified=True
        )
        ContactEmail.objects.create(
            member=member, email_address="oldsec@example.com", email_type="secondary", verified=True
        )
        ContactPhone.objects.create(member=member, phone_number="2095550000", region="1-US")
        workbook = self._build_full_workbook(
            [
                ["repl@example.com", "Old", "Name", "", "+12095557777", "Org"],
            ]
        )
        result = import_members_from_excel(workbook, update_existing=True)
        member.refresh_from_db()
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(member.organization, "Org")
        self.assertTrue(ContactEmail.objects.filter(member=member, email_address="oldsec@example.com").exists())
        self.assertTrue(ContactPhone.objects.filter(member=member, phone_number="2095557777").exists())
        self.assertTrue(ContactPhone.objects.filter(member=member, phone_number="2095550000").exists())
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Row 2: Secondary Email is blank; kept oldsec@example.com", result.warnings[0])
        self.assertIn(
            "Adds phone +12095557777 (unverified, not subscribed); keeps +12095550000", result.details[0]["changes"][1]
        )

    def test_update_existing_secondary_address_needs_a_decision(self):
        # The address is only a member's *secondary* (Row 5): without a review the row is skipped, the message says
        # whose secondary it is, and nothing changes (the blank cells delete nothing).
        member = Member.objects.create_user(password="StrongPass123!", first_name="Old", last_name="Name")
        ContactEmail.objects.create(
            member=member, email_address="ghost@example.com", email_type="secondary", verified=True
        )
        workbook = self._build_workbook([["ghost@example.com", "Old", "Name", "Org"]])

        result = import_members_from_excel(workbook, update_existing=True)

        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("needs a decision (C7: The address is a member's secondary or other email)", result.errors[0])
        self.assertIn(f"ghost@example.com is the secondary email of Old Name (member {member.pk})", result.errors[0])
        member.refresh_from_db()
        self.assertIsNone(member.organization)
        self.assertTrue(ContactEmail.objects.filter(email_address="ghost@example.com", member=member).exists())

    def test_a_failing_update_writes_nothing(self):
        member = Member.objects.create_user(password="StrongPass123!", first_name="Old", last_name="Name")
        ContactEmail.objects.create(
            member=member, email_address="errrow@example.com", email_type="primary", verified=True
        )
        workbook = self._build_workbook(
            [["new@example.com", "New", "Person", "Org"], ["errrow@example.com", "Old", "Name", "Org"]]
        )

        with patch(
            "apps.authn.services.members.import_.review.apply.rows.execute_update",
            side_effect=RuntimeError("update boom"),
        ):
            result = import_members_from_excel(workbook, update_existing=True)

        self.assertFalse(result.success)
        self.assertEqual(result.errors, ["Error importing members: update boom. Nothing was imported"])
        self.assertFalse(ContactEmail.objects.filter(email_address="new@example.com").exists())
        member.refresh_from_db()
        self.assertIsNone(member.organization)
