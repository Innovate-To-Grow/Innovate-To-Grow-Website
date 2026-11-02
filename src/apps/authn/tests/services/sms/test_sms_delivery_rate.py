"""OTP SMS under the delivery-rate limiter: a number at its hourly cap is refused before it takes the shared slot; the
slot is taken before the number is locked or anything is reserved, so SMS delivery held back raises
``PhoneVerificationBusy`` without spending the hourly cap or the daily budget, and a refusal after the admission gives
the slot back. The views answer it with 503 and Retry-After."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import PhoneVerificationChallenge, SendQuotaWindow
from apps.authn.services.send_verification.outcomes import SendOutcome
from apps.authn.services.sms import PhoneVerificationBusy, PhoneVerificationThrottled, start_phone_verification
from apps.authn.services.sms.sns_verify import MAX_SENDS_PER_HOUR
from apps.authn.tests.sms_provider import patch_sms_provider, sms_budget_used
from apps.authn.views.helpers import challenge_error_response
from apps.core.models import AWSCredentialConfig, DeliveryRateState
from apps.core.services.delivery_rates.runtime import context

PHONE = "+12095550101"
IDENTITY = "us-west-2:+12065550000"
LOCK = "apps.authn.services.sms.sns_verify._lock_phone"
ADMIT = "apps.authn.services.sms.sns_verify._admit_otp"
PRE_CHECK = "apps.authn.services.sms.sns_verify._refuse_capped_number"
CLIENT = "apps.core.services.aws.sms_send.boto3.client"


def hold_back_sms(seconds=600, reason="spend_limit"):
    """Stop the OTP sender's SMS identity with an open breaker, as AWS's spend limit would."""
    now = context.clock()
    return DeliveryRateState.objects.create(
        channel="sms_send",
        identity=IDENTITY,
        cooldown_group="sms:us-west-2",
        breaker_state=DeliveryRateState.BreakerState.OPEN,
        breaker_scope=DeliveryRateState.BreakerScope.ALL,
        breaker_reason=reason,
        breaker_retry_at=now + timedelta(seconds=seconds),
        breaker_interval_seconds=seconds,
    )


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class OtpAdmissionTests(TestCase):
    def setUp(self):
        cache.clear()
        AWSCredentialConfig.objects.all().delete()
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
        )
        patcher = patch(CLIENT)
        self.client_factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.provider = self.client_factory.return_value
        self.provider.send_text_message.return_value = {"MessageId": "otp-1"}

    def test_held_back_sms_is_busy_before_the_number_is_locked_or_any_budget_is_spent(self):
        hold_back_sms(seconds=600)

        with patch(LOCK) as lock, self.assertRaises(PhoneVerificationBusy) as caught:
            start_phone_verification(PHONE)

        lock.assert_not_called()
        self.assertEqual(caught.exception.retry_after, 600)
        self.assertEqual(caught.exception.outcome, "transient")
        self.assertEqual(
            str(caught.exception), "SMS delivery is busy right now; please try again in about 600 seconds."
        )
        self.assertFalse(PhoneVerificationChallenge.objects.exists())
        self.assertFalse(SendQuotaWindow.objects.exists())
        self.provider.send_text_message.assert_not_called()

    def test_a_sent_code_is_recorded_on_the_sms_identity(self):
        start_phone_verification(PHONE)

        state = DeliveryRateState.objects.get(channel="sms_send", identity=IDENTITY)
        self.assertEqual(state.last_signal, "ok")
        self.assertIsNotNone(state.tat)

    def cap_the_number(self):
        PhoneVerificationChallenge.objects.bulk_create(
            PhoneVerificationChallenge(
                phone_number=PHONE,
                purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
                code_hash=make_password("123456"),
                status=PhoneVerificationChallenge.Status.EXPIRED,
                expires_at=timezone.now(),
                send_reserved_at=timezone.now(),
            )
            for _index in range(MAX_SENDS_PER_HOUR)
        )

    def test_a_capped_number_is_refused_before_it_takes_the_shared_sms_slot(self):
        # Requests for capped numbers must not advance the pace genuine codes for other numbers wait for.
        self.cap_the_number()

        with patch(ADMIT) as admit, self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(PHONE)

        admit.assert_not_called()
        self.assertFalse(DeliveryRateState.objects.filter(channel="sms_send").exists())
        self.provider.send_text_message.assert_not_called()

    def test_the_cap_reached_after_the_admission_gives_the_slot_back(self):
        self.cap_the_number()

        # As if another request filled the hour between the plain read and the locked re-check.
        with patch(PRE_CHECK), self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(PHONE)

        state = DeliveryRateState.objects.get(channel="sms_send", identity=IDENTITY)
        self.assertIsNone(state.tat)  # the slot taken before the cap refused it is free again
        self.provider.send_text_message.assert_not_called()

    def test_aws_throttling_is_busy_and_the_code_cannot_be_used(self):
        self.provider.send_text_message.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "SendTextMessage"
        )

        with self.assertRaises(PhoneVerificationBusy) as caught:
            start_phone_verification(PHONE)

        self.assertGreaterEqual(caught.exception.retry_after, 1)
        challenge = PhoneVerificationChallenge.objects.get()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.EXPIRED)
        self.assertEqual(caught.exception.challenge_id, str(challenge.pk))


class BusyResponseTests(TestCase):
    def test_busy_is_a_503_that_says_when_to_ask_again(self):
        response = challenge_error_response(PhoneVerificationBusy(12))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "12")
        self.assertEqual(response.data["retry_after"], 12)
        self.assertIn("about 12 seconds", response.data["detail"])

    def test_the_event_registration_send_reports_busy_as_definitely_not_sent(self):
        from apps.event.views.registration.sms import _send_registration_code

        with patch("apps.authn.services.sms.start_phone_verification", side_effect=PhoneVerificationBusy(30)):
            outcome = _send_registration_code(MagicMock(), PHONE, "event-registration:1")

        self.assertIsInstance(outcome, SendOutcome)
        self.assertEqual((outcome.http_status, outcome.status), (503, "definitely_failed"))
        self.assertEqual(outcome.payload["retry_after"], 30)


@override_settings(SEND_VERIFICATION_MODE="observe", SEND_VERIFICATION_TEST_AUTOSOLVE=False)
class BusyPhoneAuthApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.publish = patch_sms_provider(self)

    def test_a_phone_login_code_held_back_answers_503_with_retry_after(self):
        hold_back_sms(seconds=120)

        response = self.client.post("/authn/phone-auth/request-code/", {"phone_number": "2095550101"}, format="json")

        self.assertEqual(response.status_code, 503, response.data)
        self.assertEqual(response["Retry-After"], "120")
        self.assertEqual(response.data["retry_after"], 120)
        self.publish.assert_not_called()
        self.assertEqual(sms_budget_used(), 0)
