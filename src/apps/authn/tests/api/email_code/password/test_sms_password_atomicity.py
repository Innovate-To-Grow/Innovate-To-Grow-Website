from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import (
    ContactEmail,
    ContactPhone,
    EmailAuthChallenge,
    PhoneVerificationChallenge,
)
from apps.authn.services import (
    verify_sms_password_code_and_mint,
)
from apps.authn.tests.api.email_code.password.test_password_change_sms import (
    CONFIRM_URL,
    NEW_PASSWORD,
    REQUEST_URL,
    VERIFY_URL,
    Member,
)


class SmsPasswordAtomicityTests(APITestCase):
    def setUp(self):
        self.member = Member.objects.create_user(is_active=True)
        self.e164 = "+12095551234"
        self.purpose = EmailAuthChallenge.Purpose.PASSWORD_CHANGE
        self.challenge = PhoneVerificationChallenge.objects.create(
            phone_number=self.e164,
            purpose=self.purpose,
            member=self.member,
            context_identifier=f"{self.purpose}:{self.member.pk}",
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )

    def test_token_insert_failure_rolls_back_sms_consumption(self):
        with (
            patch.object(
                EmailAuthChallenge.objects,
                "create",
                side_effect=RuntimeError("token row unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            verify_sms_password_code_and_mint(
                member=self.member,
                purpose=self.purpose,
                e164=self.e164,
                code="123456",
                challenge_id=self.challenge.pk,
            )

        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, PhoneVerificationChallenge.Status.PENDING)
        self.assertFalse(
            EmailAuthChallenge.objects.filter(
                member=self.member,
                purpose=self.purpose,
                channel=EmailAuthChallenge.Channel.SMS,
            ).exists()
        )


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class PasswordChannelSelectionTests(APITestCase):
    """The change-password flow prefers a verified email over SMS when one exists."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(is_active=True, first_name="Eve", last_name="Email")
        self.member.set_unusable_password()
        self.member.save()
        ContactPhone.objects.create(member=self.member, phone_number="2095559999", region="1-US", verified=True)
        self.client.force_authenticate(user=self.member)

    def _email_flow(self, email_address):
        request = self.client.post(REQUEST_URL, {}, format="json")
        self.assertEqual(request.status_code, 202)
        self.assertEqual(request.data["channel"], "email")
        verify = self.client.post(VERIFY_URL, {"email": email_address, "code": "654321"}, format="json")
        self.assertEqual(verify.status_code, 200)
        token = verify.data["verification_token"]
        confirm = self.client.post(
            CONFIRM_URL,
            {"verification_token": token, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(NEW_PASSWORD))

    def test_phone_first_user_can_create_password_after_verifying_email(self, _mock_code, _mock_send):
        # Phone-first member adds a (now primary) verified email, then sets a password.
        ContactEmail.objects.create(
            member=self.member, email_address="eve@example.com", email_type="primary", verified=True
        )
        self._email_flow("eve@example.com")

    def test_verified_non_primary_email_used_when_no_primary(self, _mock_code, _mock_send):
        # No primary email exists, only a verified secondary; it must still work.
        ContactEmail.objects.create(
            member=self.member, email_address="eve-alt@example.com", email_type="secondary", verified=True
        )
        self.assertEqual(self.member.get_primary_email(), "")
        self._email_flow("eve-alt@example.com")
