"""Unit tests for the passwordless phone-auth service + Member.get_primary_phone()."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.authn.models import ContactPhone
from apps.authn.services.contacts.phone_auth import PhoneAccountInactive, resolve_or_create_member_by_phone
from apps.authn.services.email_challenges import AuthChallengeInvalid

Member = get_user_model()


class ResolveOrCreateMemberByPhoneTests(TestCase):
    def test_creates_new_account_when_no_phone(self):
        member, flow = resolve_or_create_member_by_phone("2025550123", "1-US")
        self.assertEqual(flow, "register")
        self.assertTrue(member.is_active)
        self.assertTrue(member.requires_profile_completion)
        contact = ContactPhone.objects.get(phone_number="2025550123")
        self.assertEqual(contact.member_id, member.id)
        self.assertTrue(contact.verified)

    def test_normalizes_input_formats(self):
        member, flow = resolve_or_create_member_by_phone("+1 (202) 555-0123", "1-US")
        self.assertEqual(flow, "register")
        self.assertTrue(ContactPhone.objects.filter(phone_number="2025550123", member=member).exists())

    def test_logs_in_existing_active_member(self):
        existing = Member.objects.create_user(is_active=True, first_name="A", last_name="B")
        ContactPhone.objects.create(member=existing, phone_number="2025550123", region="1-US", verified=True)
        member, flow = resolve_or_create_member_by_phone("2025550123", "1-US")
        self.assertEqual(flow, "login")
        self.assertEqual(member.id, existing.id)

    def test_rejects_inactive_member_on_login_without_mutating(self):
        # A disabled account must not be silently revived by proving phone
        # ownership (mirrors the email-code login policy). The guard runs before
        # any write, so the member stays inactive and the phone stays unverified.
        existing = Member.objects.create_user(is_active=False)
        ContactPhone.objects.create(member=existing, phone_number="2025550123", region="1-US", verified=False)
        with self.assertRaises(PhoneAccountInactive):
            resolve_or_create_member_by_phone("2025550123", "1-US")
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)
        self.assertFalse(ContactPhone.objects.get(phone_number="2025550123").verified)

    def test_claims_orphan_member_less_phone(self):
        ContactPhone.objects.create(member=None, phone_number="2025550123", region="1-US", verified=False)
        member, flow = resolve_or_create_member_by_phone("2025550123", "1-US")
        self.assertEqual(flow, "register")
        contact = ContactPhone.objects.get(phone_number="2025550123")
        self.assertEqual(contact.member_id, member.id)
        self.assertTrue(contact.verified)

    @patch("apps.authn.services.contacts.phone_auth.create_contact_phone", side_effect=AuthChallengeInvalid("dup"))
    def test_create_failure_without_existing_row_reraises_and_rolls_back_member(self, _mock_create):
        before = Member.objects.count()
        with self.assertRaises(AuthChallengeInvalid):
            resolve_or_create_member_by_phone("2025550123", "1-US")
        # The savepoint rollback must undo the throwaway member insert.
        self.assertEqual(Member.objects.count(), before)
        self.assertFalse(ContactPhone.objects.filter(phone_number="2025550123").exists())

    @patch("apps.authn.services.contacts.phone_auth.create_contact_phone", side_effect=AuthChallengeInvalid("dup"))
    @patch("apps.authn.services.contacts.phone_auth.ContactPhone")
    def test_create_race_refetches_existing_and_logs_in(self, mock_contact_phone, _mock_create):
        winner = Member.objects.create_user(is_active=True, first_name="W", last_name="X")
        competitor = MagicMock()
        competitor.member = winner
        competitor.verified = True
        chain = (
            mock_contact_phone.objects.select_for_update.return_value.select_related.return_value.filter.return_value
        )
        # First lookup misses; after the unique-constraint race, the re-fetch finds the winner.
        chain.first.side_effect = [None, competitor]

        member, flow = resolve_or_create_member_by_phone("2025550123", "1-US")
        self.assertEqual(flow, "login")
        self.assertEqual(member, winner)


class GetPrimaryPhoneTests(TestCase):
    def test_empty_when_no_phone(self):
        member = Member.objects.create_user(is_active=True)
        self.assertEqual(member.get_primary_phone(), "")

    def test_prefers_verified_phone(self):
        member = Member.objects.create_user(is_active=True)
        ContactPhone.objects.create(member=member, phone_number="2025550001", region="1-US", verified=False)
        ContactPhone.objects.create(member=member, phone_number="2025550002", region="1-US", verified=True)
        self.assertEqual(member.get_primary_phone(), "+12025550002")

    def test_falls_back_to_earliest_when_none_verified(self):
        member = Member.objects.create_user(is_active=True)
        ContactPhone.objects.create(member=member, phone_number="2025550001", region="1-US", verified=False)
        self.assertEqual(member.get_primary_phone(), "+12025550001")
