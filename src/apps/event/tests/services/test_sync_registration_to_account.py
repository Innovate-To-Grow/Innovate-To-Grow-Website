from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase

from apps.authn.models import ContactPhone
from apps.event.services.registration.sync_account import sync_name_to_account, sync_phone_to_account
from apps.event.tests.helpers import make_member


class SyncNameToAccountTest(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="sync@example.com", first_name="Original", last_name="Name")

    def test_updates_both_names(self):
        sync_name_to_account(self.member, "New", "Last")
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "New")
        self.assertEqual(self.member.last_name, "Last")

    def test_updates_first_name_only(self):
        sync_name_to_account(self.member, "Updated", "")
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Updated")
        self.assertEqual(self.member.last_name, "Name")

    def test_updates_last_name_only(self):
        sync_name_to_account(self.member, "", "Updated")
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Original")
        self.assertEqual(self.member.last_name, "Updated")

    def test_empty_strings_do_not_clear_names(self):
        sync_name_to_account(self.member, "", "")
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Original")
        self.assertEqual(self.member.last_name, "Name")

    def test_same_values_no_save(self):
        with patch.object(self.member, "save") as mock_save:
            sync_name_to_account(self.member, "Original", "Name")
            mock_save.assert_not_called()

    def test_partial_update_saves(self):
        sync_name_to_account(self.member, "Changed", "Name")
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Changed")


class SyncPhoneToAccountTest(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="phone@example.com")

    def test_creates_new_phone(self):
        sync_phone_to_account(self.member, "+12095551234")
        phone = ContactPhone.objects.get(member=self.member)
        self.assertEqual(phone.phone_number, "2095551234")
        self.assertFalse(phone.verified)

    def test_creates_verified_phone(self):
        sync_phone_to_account(self.member, "+12095551234", verified=True)
        phone = ContactPhone.objects.get(member=self.member)
        self.assertTrue(phone.verified)

    def test_empty_phone_does_nothing(self):
        sync_phone_to_account(self.member, "")
        self.assertEqual(ContactPhone.objects.count(), 0)

    def test_whitespace_only_does_nothing(self):
        sync_phone_to_account(self.member, "   ")
        self.assertEqual(ContactPhone.objects.count(), 0)

    def test_existing_phone_same_member_marks_verified(self):
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US", verified=False)
        sync_phone_to_account(self.member, "+12095551234", verified=True)
        phone = ContactPhone.objects.get(member=self.member)
        self.assertTrue(phone.verified)

    def test_existing_phone_same_member_already_verified_no_change(self):
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US", verified=True)
        sync_phone_to_account(self.member, "+12095551234", verified=False)
        phone = ContactPhone.objects.get(member=self.member)
        self.assertTrue(phone.verified)

    def test_phone_owned_by_another_member_not_stolen(self):
        other = make_member(email="other@example.com")
        ContactPhone.objects.create(member=other, phone_number="2095551234", region="1-US", verified=True)

        sync_phone_to_account(self.member, "+12095551234")
        self.assertEqual(ContactPhone.objects.filter(member=self.member).count(), 0)
        self.assertEqual(ContactPhone.objects.get(phone_number="2095551234").member, other)

    def test_stale_phone_read_cannot_verify_changed_owner_number_or_region(self):
        other = make_member(email="other@example.com")
        for changes in (
            {"member": other},
            {"phone_number": "2095559999"},
            {"region": "44-GB"},
        ):
            with self.subTest(changes=changes):
                phone = ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US")
                ContactPhone.objects.filter(pk=phone.pk).update(**changes)
                with patch("django.db.models.query.QuerySet.first", return_value=phone):
                    sync_phone_to_account(self.member, "+12095551234", verified=True)
                phone.refresh_from_db()
                self.assertFalse(phone.verified)
                phone.delete()

    def test_concurrent_insert_conflict_does_not_break_registration_transaction(self):
        ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US")
        with patch("django.db.models.query.QuerySet.first", return_value=None):
            sync_phone_to_account(self.member, "+12095551234", verified=True)
        self.assertEqual(ContactPhone.objects.filter(member=self.member).count(), 1)

    @patch("apps.event.services.registration.sync_account.ContactPhone.objects.create")
    def test_integrity_error_swallowed(self, mock_create):
        mock_create.side_effect = IntegrityError("duplicate")
        sync_phone_to_account(self.member, "+12095559999")
        self.assertEqual(ContactPhone.objects.filter(member=self.member).count(), 0)
