"""Final mop-up coverage for assorted authn modules."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.authn.backends import EmailAuthBackend
from apps.authn.models import ContactEmail, RSAKeypair
from apps.authn.services.email_challenges import _random_code
from apps.authn.services.export_members_vcf import _build_vcard, _escape, _profile_image
from apps.authn.services.member_sheet_sync import MemberSyncError
from apps.authn.services.rsa_manager import (
    RSADecryptionError,
    decrypt_password,
    get_or_create_auth_keypair,
)
from apps.authn.services.unsubscribe_token import build_unsubscribe_url

Member = get_user_model()


def _member(**kw):
    return Member.objects.create_user(
        password="StrongPass123!",
        first_name=kw.pop("first_name", "A"),
        last_name=kw.pop("last_name", "B"),
        **kw,
    )


class EmailAuthBackendTests(TestCase):
    def test_username_falls_back_to_email_kwarg(self):
        member = _member(is_active=True)
        ContactEmail.objects.create(member=member, email_address="b@example.com", email_type="primary", verified=True)
        backend = EmailAuthBackend()
        result = backend.authenticate(None, email="b@example.com", password="StrongPass123!")
        self.assertEqual(result, member)

    def test_missing_password_returns_none(self):
        backend = EmailAuthBackend()
        self.assertIsNone(backend.authenticate(None, username="b@example.com", password=None))

    def test_unknown_email_returns_none(self):
        backend = EmailAuthBackend()
        self.assertIsNone(backend.authenticate(None, username="nobody@example.com", password="x"))


class RandomCodeTests(TestCase):
    def test_random_code_is_six_digits(self):
        code = _random_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())


class RsaManagerEdgeTests(TestCase):
    def setUp(self):
        RSAKeypair.objects.all().delete()

    def test_decrypt_with_unknown_key_id_falls_back_to_active(self):
        # An unknown key_id falls back to the active keypair (lines 98-100), then fails to
        # decrypt arbitrary bytes -> RSADecryptionError (lines 124-125).
        get_or_create_auth_keypair()
        with self.assertRaises(RSADecryptionError):
            decrypt_password("bm90LXZhbGlkLWVuY3J5cHRlZA==", key_id="00000000-0000-0000-0000-000000000000")

    def test_get_or_create_deactivates_duplicate_actives(self):
        # Two active keypairs with the auth name -> the older is deactivated (line 47).
        from apps.authn.services.rsa_manager import AUTH_KEY_NAME

        RSAKeypair.objects.create(name=AUTH_KEY_NAME, is_active=True)
        RSAKeypair.objects.create(name=AUTH_KEY_NAME, is_active=True)
        get_or_create_auth_keypair()
        active = RSAKeypair.objects.filter(name=AUTH_KEY_NAME, is_active=True)
        self.assertEqual(active.count(), 1)

    @patch("apps.authn.services.rsa_manager.rotate_auth_keypair")
    def test_get_or_create_rotates_stale_key(self, mock_rotate):
        from datetime import timedelta

        from django.utils import timezone

        from apps.authn.services.rsa_manager import AUTH_KEY_NAME

        keypair = RSAKeypair.objects.create(name=AUTH_KEY_NAME, is_active=True)
        RSAKeypair.objects.filter(pk=keypair.pk).update(created_at=timezone.now() - timedelta(days=2))
        get_or_create_auth_keypair()
        mock_rotate.assert_called_once()


class ExportVcfHelperTests(TestCase):
    def test_escape_none_returns_empty(self):
        self.assertEqual(_escape(None), "")

    def test_profile_image_raw_without_data_uri(self):
        payload, mime = _profile_image("rawbase64data")
        self.assertEqual(payload, "rawbase64data")
        self.assertEqual(mime, "")

    def test__build_vcard_uses_email_when_no_name(self):
        member = Member.objects.create_user(password="StrongPass123!", first_name="", last_name="")
        ContactEmail.objects.create(
            member=member, email_address="noname@example.com", email_type="primary", verified=True
        )
        member.refresh_from_db()
        card = _build_vcard(member)
        self.assertIn("noname@example.com", card)

    def test__build_vcard_phone_e164_failure_omits_tel(self):
        from apps.authn.models import ContactPhone

        member = _member()
        ContactEmail.objects.create(member=member, email_address="p@example.com", email_type="primary", verified=True)
        ContactPhone.objects.create(member=member, phone_number="2095551234", region="1-US")
        member.refresh_from_db()
        # to_e164() raising -> the TEL line is omitted (lines 75-76 + the `if tel` guard).
        with patch.object(ContactPhone, "to_e164", side_effect=RuntimeError("bad region")):
            card = _build_vcard(member)
        self.assertNotIn("TEL", card)


class UnsubscribeUrlTests(TestCase):
    def test_build_unsubscribe_url_contains_token(self):
        member = _member(is_active=True)
        url = build_unsubscribe_url(member)
        self.assertIn("/unsubscribe-login?token=", url)


class SyncMembersCommandTests(TestCase):
    @patch("apps.authn.management.commands.sync_members_to_sheet.sync_members_to_sheet", return_value=4)
    def test_command_success(self, mock_sync):
        from io import StringIO

        out = StringIO()
        call_command("sync_members_to_sheet", stdout=out)
        self.assertIn("Synced 4 members to sheet.", out.getvalue())

    @patch(
        "apps.authn.management.commands.sync_members_to_sheet.sync_members_to_sheet",
        side_effect=MemberSyncError("not configured"),
    )
    def test_command_failure_raises_command_error(self, mock_sync):
        with self.assertRaisesMessage(CommandError, "Sync failed: not configured"):
            call_command("sync_members_to_sheet")
