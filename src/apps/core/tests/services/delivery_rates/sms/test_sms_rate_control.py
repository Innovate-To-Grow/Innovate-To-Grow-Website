"""Every SMS goes through ``send_text_message`` under the delivery-rate limiter: AWS's answers (stubbed with botocore's
Stubber, the ``Reason`` as a modeled field) become rate signals, holds come back as ``SmsRateDeferred`` before any
provider call, and the worker finds the SMS identity in use."""

import boto3
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from django.test import SimpleTestCase

from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.adapters.sms import sms_signal

REGION = "us-west-2"
NUMBER = "+12065550000"
IDENTITY = f"{REGION}:{NUMBER}"
SENT = {"MessageId": "sms-1"}
CLIENT = "apps.core.services.aws.sms_send.boto3.client"


def stubbed_client():
    client = boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=REGION,
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
    )
    return client, Stubber(client)


def add_error(stubber, code, reason=None, status=400):
    stubber.add_client_error(
        "send_text_message",
        service_error_code=code,
        service_message="refused",
        http_status_code=status,
        modeled_fields={"Reason": reason} if reason else None,
    )


def client_error(code, reason=None):
    client, stubber = stubbed_client()
    add_error(stubber, code, reason)
    with stubber:
        try:
            client.send_text_message(DestinationPhoneNumber="+12095550101", OriginationIdentity=NUMBER, MessageBody="x")
        except Exception as exc:  # noqa: BLE001 - the stubbed refusal is the value under test
            return exc
    raise AssertionError("the stub did not refuse")


class SmsSignalTests(SimpleTestCase):
    def test_answers_become_signals_by_code_and_top_level_reason(self):
        cases = [
            ("ThrottlingException", None, rates.SignalKind.THROTTLE, "throttled"),
            ("ServiceQuotaExceededException", "MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT", "blocked", "spend_limit"),
            ("AccessDeniedException", "ACCOUNT_DISABLED", rates.SignalKind.BLOCKED, "account_blocked"),
            ("AccessDeniedException", "INSUFFICIENT_ACCOUNT_REPUTATION", rates.SignalKind.BLOCKED, "account_blocked"),
            ("ConflictException", "NO_ORIGINATION_IDENTITIES_FOUND", rates.SignalKind.BLOCKED, rates.Reason.PERMISSION),
            ("ConflictException", "DESTINATION_PHONE_NUMBER_OPTED_OUT", rates.SignalKind.NONE, "message_rejected"),
            ("ValidationException", "INVALID_PARAMETER", rates.SignalKind.NONE, "message_rejected"),
            ("InternalServerException", None, rates.SignalKind.NONE, "provider_error"),
        ]
        for code, reason, kind, why in cases:
            with self.subTest(code=code, reason=reason):
                signal = sms_signal(client_error(code, reason))
                self.assertEqual((signal.kind, signal.reason), (kind, why))

    def test_the_spend_limit_stops_every_lane_and_probes_hourly(self):
        signal = sms_signal(client_error("ServiceQuotaExceededException", "MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT"))

        self.assertEqual((signal.scope, signal.breaker_seconds), (rates.Scope.ALL, 3600))
        self.assertTrue(rates.not_now(signal))
        # A configuration save may fix a missing origination identity; it cannot fix a disabled account.
        self.assertFalse(
            rates.not_now(sms_signal(client_error("ConflictException", "NO_ORIGINATION_IDENTITIES_FOUND")))
        )
        self.assertTrue(rates.not_now(sms_signal(client_error("AccessDeniedException", "ACCOUNT_DISABLED"))))

    def test_a_failure_without_an_answer_is_no_signal(self):
        self.assertIsNone(sms_signal(EndpointConnectionError(endpoint_url="https://sms-voice.us-west-2.amazonaws.com")))
        self.assertIsNone(sms_signal(RuntimeError("no answer")))
