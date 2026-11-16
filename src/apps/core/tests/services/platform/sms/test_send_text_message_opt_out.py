from unittest.mock import Mock, patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws import sms_send
from apps.core.services.aws.sms_errors import SmsOptedOut
from apps.core.services.delivery_rates import Lane
from apps.core.tests.services.platform.sms.test_sms_opt_outs import DESTINATION, NUMBER, REGION, hooks, stubbed_client


class SendTextMessageOptOutTests(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.create(
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region=REGION,
            sms_from_number=NUMBER,
        )
        self.client, self.stubber = stubbed_client()
        self.stubber.activate()
        self.addCleanup(self.stubber.deactivate)
        patcher = patch("apps.core.services.aws.sms_send.boto3.client", return_value=self.client)
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_opted_out_destination_is_refused_before_any_client_or_admission(self):
        with (
            hooks(is_opted_out=lambda number: True),
            patch.object(sms_send, "admit_text") as admit,
            self.assertRaises(SmsOptedOut),
        ):
            sms_send.send_text_message(DESTINATION, "Hello")
        self.factory.assert_not_called()
        admit.assert_not_called()
        self.stubber.assert_no_pending_responses()

    def test_a_refusal_releases_an_admission_the_caller_took(self):
        admission = sms_send.admit_text(sms_send.resolve_sender(), "Hello", lane=Lane.TRANSACTIONAL)
        with (
            hooks(is_opted_out=lambda number: True),
            patch.object(sms_send, "_settle", wraps=sms_send._settle) as settle,
            self.assertRaises(SmsOptedOut),
        ):
            sms_send.send_text_message(DESTINATION, "Hello", admission=admission)
        settle.assert_called_once_with(admission, None)

    def test_aws_refusing_an_opted_out_destination_is_recorded_on_the_list(self):
        record = Mock()
        self.stubber.add_client_error(
            "send_text_message",
            service_error_code="ConflictException",
            service_message="opted out",
            http_status_code=400,
            modeled_fields={"Reason": "DESTINATION_PHONE_NUMBER_OPTED_OUT"},
        )
        with (
            hooks(is_opted_out=lambda number: False, record_refusal=record),
            self.assertLogs("apps.core.services.aws.sms_send", level="WARNING"),
            self.assertRaises(SmsOptedOut) as caught,
        ):
            sms_send.send_text_message(DESTINATION, "Hello")
        self.assertTrue(caught.exception.refused_by_provider)
        self.assertFalse(caught.exception.held_back)
        record.assert_called_once_with(DESTINATION)

    def test_a_destination_not_on_the_list_is_sent(self):
        self.stubber.add_response(
            "send_text_message",
            {"MessageId": "sms-1"},
            {
                "DestinationPhoneNumber": DESTINATION,
                "OriginationIdentity": NUMBER,
                "MessageBody": "Hello",
                "MessageType": "TRANSACTIONAL",
            },
        )
        with hooks(is_opted_out=lambda number: False):
            self.assertEqual(sms_send.send_text_message(DESTINATION, "Hello"), "sms-1")
