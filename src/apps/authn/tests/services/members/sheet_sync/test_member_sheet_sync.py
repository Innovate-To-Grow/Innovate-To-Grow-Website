"""Tests for member-to-Google-Sheet sync service."""

from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, Member, MemberSheetSyncConfig
from apps.authn.services.members.sheet_sync import (
    MemberSyncError,
    _build_header,
    _build_row,
    sync_members_to_sheet,
)


def _create_member(first="Alice", middle="", last="Smith", org="Acme", title="Dev", active=True):
    member = Member.objects.create_user(
        password="TestPass123!",
        first_name=first,
        middle_name=middle or "",
        last_name=last,
        organization=org,
        title=title,
        is_active=active,
    )
    ContactEmail.objects.create(member=member, email_address=f"{first.lower()}@example.com", email_type="primary")
    return member


def _enable_config(sheet_id="test-sheet-id", auto_sync=True):
    return MemberSheetSyncConfig.objects.create(is_enabled=True, auto_sync_enabled=auto_sync, google_sheet_id=sheet_id)


class BuildHeaderTests(TestCase):
    def test_header_columns(self):
        header = _build_header()
        self.assertEqual(
            header,
            [
                "UUID",
                "First Name",
                "Middle Name",
                "Last Name",
                "Primary Email",
                "Primary Phone",
                "Organization",
                "Title",
                "Date Joined (UTC)",
                "Last Updated (UTC)",
                "Active",
            ],
        )


class BuildRowTests(TestCase):
    def test_basic_row(self):
        member = _create_member()
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[0], str(member.id))
        self.assertEqual(row[1], "Alice")
        self.assertEqual(row[2], "")  # no middle name
        self.assertEqual(row[3], "Smith")
        self.assertEqual(row[4], "alice@example.com")
        self.assertEqual(row[5], "")  # no phone
        self.assertEqual(row[6], "Acme")
        self.assertEqual(row[7], "Dev")
        self.assertEqual(row[10], "Yes")

    def test_middle_name_present(self):
        member = _create_member(first="Bob", middle="James", last="Doe")
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[2], "James")

    def test_inactive_member(self):
        member = _create_member(first="Inactive", active=False)
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[10], "No")

    def test_phone_present(self):
        member = _create_member(first="Phoney")
        ContactPhone.objects.create(member=member, phone_number="2095551234", region="1-US")
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[5], "2095551234")

    def test_missing_email(self):
        member = Member.objects.create_user(
            password="TestPass123!", first_name="NoEmail", last_name="User", is_active=True
        )
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[4], "")


class SyncDisabledTests(TestCase):
    def test_raises_when_not_configured(self):
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet()

    def test_raises_when_disabled(self):
        MemberSheetSyncConfig.objects.create(is_enabled=False, google_sheet_id="sheet-id")
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet()

    def test_raises_when_sheet_id_empty(self):
        MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="")
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet()
