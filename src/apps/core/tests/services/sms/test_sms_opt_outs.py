"""The SMS opt-out check every send makes (``sms_opt_outs`` hooks in ``send_text_message``), AWS's opted-out refusal,
and the read-only read of AWS's opted-out list. AWS is never called: botocore's Stubber answers on a real client
(which also checks every request and answer against the service model)."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import boto3
from botocore.stub import Stubber
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.core.services.aws import sms_opt_outs
from apps.core.services.aws.credentials import AwsCredentials
from apps.core.services.aws.sms_errors import SmsDeliveryError, SmsOptedOut

REGION = "us-west-2"
NUMBER = "+12065550000"
DESTINATION = "+12095550101"
CREDENTIALS = AwsCredentials(access_key_id="test-access-key", secret_access_key="test-secret-key", region=REGION)


def stubbed_client():
    client = boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=REGION,
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
    )
    return client, Stubber(client)


def hooks(is_opted_out=None, record_refusal=None):
    """Install fake list callables for one test (mail's real ones are restored afterwards)."""
    return patch.dict(sms_opt_outs._hooks, {"is_opted_out": is_opted_out, "record_refusal": record_refusal})


def phone_number(number, *, list_name="Default", status="ACTIVE", number_id="phone-1"):
    return {
        "PhoneNumberArn": f"arn:aws:sms-voice:{REGION}:000000000000:phone-number/{number_id}",
        "PhoneNumberId": number_id,
        "PhoneNumber": number,
        "Status": status,
        "IsoCountryCode": "US",
        "MessageType": "TRANSACTIONAL",
        "NumberCapabilities": ["SMS"],
        "NumberType": "TOLL_FREE",
        "MonthlyLeasingPrice": "2.00",
        "TwoWayEnabled": False,
        "SelfManagedOptOutsEnabled": False,
        "OptOutListName": list_name,
        "DeletionProtectionEnabled": False,
        "CreatedTimestamp": datetime(2026, 1, 1, tzinfo=UTC),
    }


def opted_out_page(numbers, *, list_name="Default", next_token=None):
    page = {
        "OptOutListArn": f"arn:aws:sms-voice:{REGION}:000000000000:opt-out-list/{list_name}",
        "OptOutListName": list_name,
        "OptedOutNumbers": [
            {
                "OptedOutNumber": number,
                "OptedOutTimestamp": datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
                "EndUserOptedOut": True,
            }
            for number in numbers
        ],
    }
    if next_token:
        page["NextToken"] = next_token
    return page


class HookRegistryTests(SimpleTestCase):
    def test_registering_the_same_callables_again_is_a_no_op_and_others_are_refused(self):
        check, record = Mock(return_value=False), Mock()
        with hooks():
            sms_opt_outs.register_opt_out_list(is_opted_out=check, record_refusal=record)
            sms_opt_outs.register_opt_out_list(is_opted_out=check, record_refusal=record)
            with self.assertRaises(ImproperlyConfigured):
                sms_opt_outs.register_opt_out_list(is_opted_out=Mock(), record_refusal=record)

    def test_without_a_list_every_destination_may_be_tried(self):
        with hooks():
            sms_opt_outs.refuse_if_opted_out(DESTINATION)

    def test_a_listed_destination_is_refused(self):
        with hooks(is_opted_out=lambda number: number == DESTINATION), self.assertRaises(SmsOptedOut) as caught:
            sms_opt_outs.refuse_if_opted_out(DESTINATION)
        self.assertEqual((caught.exception.outcome, caught.exception.code), ("permanent", "OptedOut"))
        self.assertFalse(caught.exception.refused_by_provider)

    def test_a_list_that_cannot_be_read_refuses_as_transient(self):
        with (
            hooks(is_opted_out=Mock(side_effect=RuntimeError("db down"))),
            self.assertLogs("apps.core.services.aws.sms_opt_outs", level="ERROR"),
            self.assertRaises(SmsDeliveryError) as caught,
        ):
            sms_opt_outs.refuse_if_opted_out(DESTINATION)
        self.assertNotIsInstance(caught.exception, SmsOptedOut)
        self.assertEqual(caught.exception.outcome, "transient")


class OptedOutRefusalTests(SimpleTestCase):
    def refusal(self, code="ConflictException", reason="DESTINATION_PHONE_NUMBER_OPTED_OUT"):
        client, stubber = stubbed_client()
        stubber.add_client_error(
            "send_text_message",
            service_error_code=code,
            service_message="refused",
            http_status_code=400,
            modeled_fields={"Reason": reason} if reason else None,
        )
        with stubber:
            try:
                client.send_text_message(
                    DestinationPhoneNumber=DESTINATION, OriginationIdentity=NUMBER, MessageBody="x"
                )
            except Exception as exc:  # noqa: BLE001 - the stubbed refusal is the value under test
                return exc
        raise AssertionError("the stub did not refuse")

    def test_aws_naming_the_destination_opted_out_becomes_sms_opted_out_and_is_recorded(self):
        record = Mock()
        error = SmsDeliveryError("SMS rejected the request.", outcome="permanent", code="ConflictException")
        with hooks(record_refusal=record):
            result = sms_opt_outs.opted_out_refusal(self.refusal(), DESTINATION, error)
        self.assertIsInstance(result, SmsOptedOut)
        self.assertTrue(result.refused_by_provider)
        self.assertEqual(result.code, "ConflictException")
        record.assert_called_once_with(DESTINATION)

    def test_a_list_that_cannot_record_still_reports_the_refusal(self):
        error = SmsDeliveryError("SMS rejected the request.", outcome="permanent")
        with (
            hooks(record_refusal=Mock(side_effect=RuntimeError("db down"))),
            self.assertLogs("apps.core.services.aws.sms_opt_outs", level="ERROR"),
        ):
            result = sms_opt_outs.opted_out_refusal(self.refusal(), DESTINATION, error)
        self.assertIsInstance(result, SmsOptedOut)

    def test_other_refusals_and_non_aws_errors_are_unchanged(self):
        error = SmsDeliveryError("SMS rejected the request.", outcome="permanent")
        for exc in (self.refusal("ValidationException", "INVALID_PARAMETER"), self.refusal(reason=None), OSError()):
            with self.subTest(exc=exc), hooks(record_refusal=Mock()) as installed:
                self.assertIs(sms_opt_outs.opted_out_refusal(exc, DESTINATION, error), error)
                installed["record_refusal"].assert_not_called()
