"""Sign-in and verification codes never go to a number on the SMS opt-out list (it replied STOP): the code request
is refused before it takes the shared SMS slot, the hourly cap or a unit of the daily budget, AWS refusing one as opted
out is reported the same way, and the views answer a 400 that says why. AWS is never called."""

from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from apps.authn.models import PhoneVerificationChallenge
from apps.authn.services.sms import PhoneNumberOptedOut, publish_plain_sms, start_phone_verification
from apps.authn.services.sms.errors import OPTED_OUT_MESSAGE
from apps.authn.services.sms.sns_verify import _verification_error
from apps.authn.tests.sms_provider import sms_budget_used
from apps.authn.views.helpers import PHONE_OPTED_OUT_CODE, challenge_error_response
from apps.core.models import AWSCredentialConfig
from apps.core.services.aws import sms_opt_outs
from apps.core.services.aws.sms_errors import SmsDeliveryError, SmsOptedOut

PHONE = "+12065551234"
CLIENT = "apps.core.services.aws.sms_send.boto3.client"


def opted_out(*numbers, record=None):
    return patch.dict(
        sms_opt_outs._hooks, {"is_opted_out": lambda number: number in numbers, "record_refusal": record or Mock()}
    )


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class StartPhoneVerificationOptOutTests(TestCase):
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

    @patch(CLIENT)
    def test_an_opted_out_number_takes_no_slot_budget_or_challenge(self, client_factory):
        with (
            opted_out(PHONE),
            patch("apps.authn.services.sms.sns_verify._admit_otp") as admit,
            self.assertRaises(PhoneNumberOptedOut) as caught,
        ):
            start_phone_verification(PHONE)

        self.assertEqual(str(caught.exception), OPTED_OUT_MESSAGE)
        self.assertEqual(caught.exception.outcome, "permanent")
        admit.assert_not_called()
        client_factory.assert_not_called()
        self.assertFalse(PhoneVerificationChallenge.objects.exists())
        self.assertEqual(sms_budget_used(), 0)

    @patch(CLIENT)
    def test_another_number_still_gets_its_code(self, client_factory):
        client = MagicMock()
        client.send_text_message.return_value = {"MessageId": "msg-1"}
        client_factory.return_value = client
        with opted_out("+12065559999"):
            result = start_phone_verification(PHONE)
        self.assertEqual(result["status"], "pending")
        client.send_text_message.assert_called_once()

    @patch(CLIENT)
    def test_aws_refusing_the_number_as_opted_out_is_reported_and_the_challenge_closed(self, client_factory):
        client = MagicMock()
        client.send_text_message.side_effect = ClientError(
            {
                "Error": {"Code": "ConflictException", "Message": "opted out"},
                "Reason": "DESTINATION_PHONE_NUMBER_OPTED_OUT",
                "ResponseMetadata": {"HTTPStatusCode": 400},
            },
            "SendTextMessage",
        )
        client_factory.return_value = client
        record = Mock()

        with (
            opted_out(record=record),
            self.assertLogs("apps.core.services.aws.sms_send", level="WARNING"),
            self.assertRaises(PhoneNumberOptedOut),
        ):
            start_phone_verification(PHONE)

        record.assert_called_once_with(PHONE)
        challenge = PhoneVerificationChallenge.objects.get()
        self.assertEqual(challenge.status, PhoneVerificationChallenge.Status.EXPIRED)

    @patch(CLIENT)
    def test_a_plain_sms_to_an_opted_out_number_is_refused(self, client_factory):
        with opted_out(PHONE), self.assertRaises(PhoneNumberOptedOut):
            publish_plain_sms(phone_number=PHONE, message="Test")
        client_factory.assert_not_called()


class OptedOutErrorMappingTests(SimpleTestCase):
    def test_the_send_refusal_becomes_the_verification_error(self):
        self.assertIsInstance(_verification_error(SmsOptedOut(code="OptedOut")), PhoneNumberOptedOut)

    def test_other_send_failures_keep_their_mapping(self):
        error = _verification_error(SmsDeliveryError("rejected", outcome="permanent", code="ConflictException"))
        self.assertNotIsInstance(error, PhoneNumberOptedOut)

    def test_the_response_is_a_400_that_says_why(self):
        response = challenge_error_response(PhoneNumberOptedOut())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": OPTED_OUT_MESSAGE, "code": PHONE_OPTED_OUT_CODE})


@patch("apps.authn.services.sms.start_phone_verification", side_effect=PhoneNumberOptedOut())
class PhoneAuthRequestOptedOutTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_the_sign_in_code_request_answers_400_with_the_reason(self, _start):
        response = self.client.post("/authn/phone-auth/request-code/", {"phone_number": "2025550123"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], PHONE_OPTED_OUT_CODE)
        self.assertEqual(response.data["detail"], OPTED_OUT_MESSAGE)
