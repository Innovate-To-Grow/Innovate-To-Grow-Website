from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import override_settings
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.sms.sns_verify import (
    MAX_VERIFY_ATTEMPTS,
    VERIFIED_GRANT_TTL_SECONDS,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    check_phone_verification,
    consume_verified_phone_challenge,
)
from apps.authn.tests.services.sms.sns_verify.test_sns_verify_service import _SnsVerifyServiceCase


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SnsVerifyServiceTest(_SnsVerifyServiceCase):
    def test_verified_grant_gets_fresh_expiry_from_successful_verification(self):
        member = get_user_model().objects.create_user(password="StrongPass123!")
        verified_at = timezone.now()
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=member,
            context_identifier="event-registration:event-1",
            code_hash=make_password("123456"),
            expires_at=verified_at + timedelta(seconds=1),
        )

        with patch("apps.authn.services.sms.sns_verify.timezone.now", return_value=verified_at):
            verified = check_phone_verification(
                self.phone,
                "123456",
                challenge_id=challenge.pk,
                purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
                member=member,
                context_identifier="event-registration:event-1",
                consume=False,
            )

        expected_expiry = verified_at + timedelta(seconds=VERIFIED_GRANT_TTL_SECONDS)
        self.assertEqual(verified.expires_at, expected_expiry)
        challenge.refresh_from_db()
        self.assertEqual(challenge.expires_at, expected_expiry)

        nearly_expired = expected_expiry - timedelta(seconds=1)
        with patch("apps.authn.services.sms.sns_verify.timezone.now", return_value=nearly_expired):
            consumed = consume_verified_phone_challenge(
                phone_number=self.phone,
                purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
                member=member,
                context_identifier="event-registration:event-1",
                challenge_id=challenge.pk,
            )
        self.assertEqual(consumed.status, PhoneVerificationChallenge.Status.CONSUMED)

    def test_verified_grant_cannot_cross_contexts(self):
        member = get_user_model().objects.create_user(password="StrongPass123!")
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
            member=member,
            context_identifier="event-registration:event-1",
            code_hash=make_password("123456"),
            status=PhoneVerificationChallenge.Status.VERIFIED,
            verified_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(PhoneVerificationInvalid):
            consume_verified_phone_challenge(
                phone_number=self.phone,
                purpose=PhoneVerificationChallenge.Purpose.EVENT_REGISTRATION,
                member=member,
                context_identifier="event-registration:event-2",
                challenge_id=challenge.pk,
            )

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.VERIFIED)

    def test_check_phone_verification_rejects_invalid_code_and_persists_attempt(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(None, "000000", challenge_id=challenge.pk)

        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 1)

    def test_check_phone_verification_throttles_after_max_attempts(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password("123456"),
            attempts=MAX_VERIFY_ATTEMPTS - 1,
            max_attempts=MAX_VERIFY_ATTEMPTS,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(PhoneVerificationThrottled):
            check_phone_verification(None, "000000", challenge_id=challenge.pk)

        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, MAX_VERIFY_ATTEMPTS)
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.EXPIRED)

    def test_consumed_challenge_cannot_be_replayed(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        check_phone_verification(None, "123456", challenge_id=challenge.pk)

        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(None, "123456", challenge_id=challenge.pk)

    def test_legacy_phone_only_verification_uses_latest_pending_challenge(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        consumed = check_phone_verification(self.phone, "123456")

        self.assertEqual(consumed.pk, challenge.pk)
        self.assertEqual(consumed.status, PhoneVerificationChallenge.Status.CONSUMED)

    def test_challenge_id_is_scoped_to_purpose(self):
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.phone,
            purpose=PhoneVerificationChallenge.Purpose.PASSWORD_RESET,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(
                None,
                "123456",
                challenge_id=challenge.pk,
                purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
            )
