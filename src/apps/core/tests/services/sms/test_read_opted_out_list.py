from datetime import UTC, datetime
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError
from django.test import SimpleTestCase

from apps.core.services.aws import sms_opt_outs
from apps.core.services.aws.credentials import AwsCredentialsError
from apps.core.tests.services.sms.test_sms_opt_outs import (
    CREDENTIALS,
    DESTINATION,
    NUMBER,
    REGION,
    opted_out_page,
    phone_number,
    stubbed_client,
)


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
