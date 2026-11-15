from unittest.mock import patch

from django.utils import timezone

from apps.authn.constants import RECOVERY_CHANNEL_UNAVAILABLE
from apps.authn.models import (
    EmailAuthChallenge,
)
from apps.authn.tests.api.email_code.password.test_password_change_sms import (
    CONFIRM_URL,
    NEW_PASSWORD,
    REQUEST_URL,
    _PhoneOnlyPasswordCreateViaSmsCase,
)


@patch("apps.authn.services.account.sms_password._check_phone_verification")
@patch("apps.authn.services.account.sms_password.start_phone_verification")
class PhoneOnlyPasswordCreateViaSmsTests(_PhoneOnlyPasswordCreateViaSmsCase):
    def test_reused_token_cannot_create_password_twice(self, mock_start, _mock_check):
        token = self._request_and_verify(mock_start, _mock_check)
        first = self.client.post(
            CONFIRM_URL,
            {"verification_token": token, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            CONFIRM_URL,
            {"verification_token": token, "new_password": "OtherPass456!", "new_password_confirm": "OtherPass456!"},
            format="json",
        )
        self.assertEqual(second.status_code, 400)

    def test_expired_token_cannot_create_password(self, mock_start, _mock_check):
        token = self._request_and_verify(mock_start, _mock_check)
        # Force the minted challenge to look expired.
        EmailAuthChallenge.objects.filter(
            member=self.member, purpose=EmailAuthChallenge.Purpose.PASSWORD_CHANGE
        ).update(expires_at=timezone.now() - timezone.timedelta(minutes=1))
        confirm = self.client.post(
            CONFIRM_URL,
            {"verification_token": token, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(confirm.status_code, 400)

    def test_no_verified_contact_returns_clear_error(self, _mock_start, _mock_check):
        # Remove the verified phone so no recovery channel remains.
        self.phone.delete()
        response = self.client.post(REQUEST_URL, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"][0]), RECOVERY_CHANNEL_UNAVAILABLE)
