"""The SMS opt-out check every send makes (``sms_opt_outs`` hooks in ``send_text_message``), AWS's opted-out refusal,
and the read-only read of AWS's opted-out list. AWS is never called: botocore's Stubber answers on a real client
(which also checks every request and answer against the service model)."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import boto3
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws import sms_opt_outs, sms_send
from apps.core.services.aws.credentials import AwsCredentials, AwsCredentialsError
from apps.core.services.aws.sms_errors import SmsDeliveryError, SmsOptedOut
from apps.core.services.delivery_rates import Lane

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


class ReadOptedOutListTests(SimpleTestCase):
    def setUp(self):
        self.client, self.stubber = stubbed_client()
        self.stubber.activate()
        self.addCleanup(self.stubber.deactivate)
        client_patcher = patch("apps.core.services.aws.sms_opt_outs.boto3.client", return_value=self.client)
        self.factory = client_patcher.start()
        self.addCleanup(client_patcher.stop)
        credentials_patcher = patch(
            "apps.core.services.aws.sms_opt_outs.resolve_aws_credentials", return_value=CREDENTIALS
        )
        credentials_patcher.start()
        self.addCleanup(credentials_patcher.stop)

    def read(self, *, origination=NUMBER, list_name="", page_size=100, max_pages=5):
        return sms_opt_outs.read_opted_out_list(
            origination=origination, list_name=list_name, page_size=page_size, max_pages=max_pages, timeout=7
        )

    def test_the_sending_numbers_list_is_read_page_by_page(self):
        self.stubber.add_response(
            "describe_phone_numbers",
            {"PhoneNumbers": [phone_number("+12065559999", number_id="other"), phone_number(NUMBER, list_name="I2G")]},
            {},
        )
        self.stubber.add_response(
            "describe_opted_out_numbers",
            opted_out_page([DESTINATION], list_name="I2G", next_token="page-2"),
            {"OptOutListName": "I2G", "MaxResults": 100},
        )
        self.stubber.add_response(
            "describe_opted_out_numbers",
            opted_out_page(["+12095550102"], list_name="I2G"),
            {"OptOutListName": "I2G", "MaxResults": 100, "NextToken": "page-2"},
        )

        listing = self.read()

        self.assertEqual(listing.list_name, "I2G")
        self.assertTrue(listing.complete)
        self.assertEqual([entry.phone_number for entry in listing.numbers], [DESTINATION, "+12095550102"])
        self.assertTrue(listing.numbers[0].end_user_opted_out)
        self.assertEqual(listing.numbers[0].opted_out_at, datetime(2026, 11, 1, 12, 0, tzinfo=UTC))
        self.stubber.assert_no_pending_responses()

    def test_the_read_uses_the_sms_region_a_bounded_timeout_and_retries(self):
        self.stubber.add_response(
            "describe_opted_out_numbers", opted_out_page([]), {"OptOutListName": "Named", "MaxResults": 100}
        )
        self.read(list_name="Named")
        call = self.factory.call_args
        self.assertEqual((call.args[0], call.kwargs["region_name"]), ("pinpoint-sms-voice-v2", REGION))
        config = call.kwargs["config"]
        self.assertEqual((config.connect_timeout, config.read_timeout), (7, 7))
        self.assertEqual(config.retries["total_max_attempts"], 3)

    def test_a_named_list_skips_the_number_lookup(self):
        self.stubber.add_response(
            "describe_opted_out_numbers",
            opted_out_page([DESTINATION], list_name="Named"),
            {"OptOutListName": "Named", "MaxResults": 100},
        )
        listing = self.read(list_name="Named")
        self.assertEqual((listing.list_name, len(listing.numbers)), ("Named", 1))

    def test_without_a_configured_number_the_first_active_sms_number_decides(self):
        self.stubber.add_response(
            "describe_phone_numbers",
            {
                "PhoneNumbers": [
                    phone_number(NUMBER, status="PENDING", list_name="Old"),
                    phone_number("+12065558888", list_name="Live"),
                ]
            },
            {},
        )
        self.stubber.add_response(
            "describe_opted_out_numbers",
            opted_out_page([], list_name="Live"),
            {"OptOutListName": "Live", "MaxResults": 100},
        )
        self.assertEqual(self.read(origination="").list_name, "Live")

    def test_a_number_not_in_the_account_reads_awss_default_list(self):
        self.stubber.add_response("describe_phone_numbers", {"PhoneNumbers": [], "NextToken": "more"}, {})
        self.stubber.add_response("describe_phone_numbers", {"PhoneNumbers": []}, {"NextToken": "more"})
        self.stubber.add_response(
            "describe_opted_out_numbers", opted_out_page([]), {"OptOutListName": "Default", "MaxResults": 100}
        )
        self.assertEqual(self.read(origination="pool-123").list_name, "Default")

    def test_a_list_longer_than_the_page_cap_is_a_partial_read(self):
        self.stubber.add_response(
            "describe_opted_out_numbers",
            opted_out_page([DESTINATION], next_token="t"),
            {"OptOutListName": "Default", "MaxResults": 1},
        )
        listing = self.read(list_name="Default", page_size=1, max_pages=1)
        self.assertFalse(listing.complete)
        self.assertEqual(len(listing.numbers), 1)

    def test_an_aws_refusal_is_a_sanitized_error_with_its_code(self):
        self.stubber.add_client_error(
            "describe_opted_out_numbers",
            service_error_code="AccessDeniedException",
            service_message="no sms-voice:Describe",
        )
        with (
            self.assertLogs("apps.core.services.aws.sms_opt_outs", level="WARNING"),
            self.assertRaises(sms_opt_outs.OptOutListError) as caught,
        ):
            self.read(list_name="Default")
        self.assertEqual(caught.exception.code, "AccessDeniedException")
        self.assertNotIn("sms-voice", str(caught.exception))

    def test_an_unreachable_aws_is_an_error_without_a_code(self):
        with (
            patch.object(
                self.client, "describe_opted_out_numbers", side_effect=EndpointConnectionError(endpoint_url="x")
            ),
            self.assertLogs("apps.core.services.aws.sms_opt_outs", level="WARNING"),
            self.assertRaises(sms_opt_outs.OptOutListError) as caught,
        ):
            self.read(list_name="Default")
        self.assertEqual(caught.exception.code, "")

    def test_missing_credentials_are_reported_as_such(self):
        with (
            patch("apps.core.services.aws.sms_opt_outs.resolve_aws_credentials", side_effect=AwsCredentialsError("x")),
            self.assertRaises(AwsCredentialsError),
        ):
            self.read()
