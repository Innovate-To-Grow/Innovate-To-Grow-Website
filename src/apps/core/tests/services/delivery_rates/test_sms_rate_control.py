"""Every SMS goes through ``send_text_message`` under the delivery-rate limiter: AWS's answers (stubbed with botocore's
Stubber, the ``Reason`` as a modeled field) become rate signals, holds come back as ``SmsRateDeferred`` before any
provider call, and the worker finds the SMS identity in use."""

from datetime import timedelta
from unittest.mock import Mock, patch

import boto3
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.core.models import AWSCredentialConfig, DeliveryRateState, DeliveryUsageBucket
from apps.core.services import delivery_rates as rates
from apps.core.services.aws import sms_send
from apps.core.services.aws.sms import _cache_key
from apps.core.services.delivery_rates.adapters.sms import sms_signal
from apps.core.services.delivery_rates.families import clear_gate_cache

from .helpers import FakeClock

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


class SendTextMessageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region=REGION,
            sms_from_number=NUMBER,
        )
        self.client, self.stubber = stubbed_client()
        self.stubber.activate()
        self.addCleanup(self.stubber.deactivate)
        patcher = patch(CLIENT, return_value=self.client)
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)

    def state(self):
        return DeliveryRateState.objects.get(channel="sms_send", identity=IDENTITY)

    def expect_send(self, body="Hello"):
        expected = {
            "DestinationPhoneNumber": "+12095550101",
            "OriginationIdentity": NUMBER,
            "MessageBody": body,
            "MessageType": "TRANSACTIONAL",
        }
        self.stubber.add_response("send_text_message", SENT, expected)

    def test_a_send_is_admitted_on_the_region_and_number_and_counts_one_message(self):
        self.expect_send()

        self.assertEqual(sms_send.send_text_message("+12095550101", "Hello"), "sms-1")

        state = self.state()
        self.assertEqual((state.cooldown_group, state.last_signal), (f"sms:{REGION}", rates.SignalKind.OK))
        bucket = DeliveryUsageBucket.objects.get(state=state)
        self.assertEqual((bucket.total, bucket.messages, bucket.bulk), (1, 1, 0))
        config = self.factory.call_args.kwargs["config"]
        self.assertEqual(config.retries["total_max_attempts"], 1)
        # channels.sms_send.request_timeout_seconds, not botocore's 60 s default.
        self.assertEqual((config.connect_timeout, config.read_timeout), (10, 10))
        self.stubber.assert_no_pending_responses()

    def test_a_message_of_several_parts_is_paced_by_its_parts(self):
        long_body = "x" * 161  # two GSM-7 parts
        self.expect_send(long_body)
        self.expect_send()

        sms_send.send_text_message("+12095550101", long_body)
        sms_send.send_text_message("+12095550101", "Hello")

        # One message part per second until AWS reports the number's rate: the second SMS waited for two parts.
        self.assertEqual(self.clock.slept, [2.0])

    def test_a_throttle_is_transient_and_says_how_long_sms_is_held(self):
        add_error(self.stubber, "ThrottlingException")

        with self.assertRaises(sms_send.SmsDeliveryError) as caught:
            sms_send.send_text_message("+12095550101", "Hello")

        error = caught.exception
        self.assertEqual((error.outcome, error.code, error.held_back), ("transient", "ThrottlingException", True))
        self.assertGreaterEqual(error.retry_after, 1)
        self.assertIsNotNone(self.state().cooldown_until)

    def test_the_spend_limit_holds_back_every_lane_without_calling_aws(self):
        add_error(self.stubber, "ServiceQuotaExceededException", "MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT")
        with self.assertRaises(sms_send.SmsDeliveryError) as caught:
            sms_send.send_text_message("+12095550101", "Hello", lane=rates.Lane.BULK)
        self.assertEqual(caught.exception.outcome, "transient")

        for lane in (rates.Lane.TRANSACTIONAL, rates.Lane.BULK):
            with self.subTest(lane=lane), self.assertRaises(sms_send.SmsRateDeferred) as held:
                sms_send.send_text_message("+12095550101", "Hello", lane=lane)
            self.assertEqual(held.exception.reason, "breaker:spend_limit")
            self.assertEqual(held.exception.outcome, "transient")
        self.stubber.assert_no_pending_responses()  # no call reached AWS while the breaker held

    def test_an_invalid_number_is_permanent_and_about_that_message_only(self):
        add_error(self.stubber, "ValidationException", "INVALID_PARAMETER")

        with self.assertRaises(sms_send.SmsDeliveryError) as caught:
            sms_send.send_text_message("+12095550101", "Hello")

        self.assertEqual((caught.exception.outcome, caught.exception.held_back), ("permanent", False))
        self.assertIsNone(self.state().cooldown_until)

    def test_a_refused_provider_call_gives_the_slot_back(self):
        refuse = Mock(side_effect=RuntimeError("claim lost"))

        with self.assertRaises(RuntimeError):
            sms_send.send_text_message("+12095550101", "Hello", before_provider_call=refuse)

        state = self.state()
        self.assertIsNone(state.tat)
        self.assertFalse(DeliveryUsageBucket.objects.filter(state=state, total__gt=0).exists())

    def test_missing_credentials_fail_before_any_slot_is_taken(self):
        with (
            patch("apps.core.services.aws.sms_send.resolve_aws_credentials", side_effect=sms_send.AwsCredentialsError),
            self.assertRaises(sms_send.SmsDeliveryError) as caught,
        ):
            sms_send.send_text_message("+12095550101", "Hello")

        self.assertEqual((str(caught.exception), caught.exception.outcome), (sms_send.CREDENTIALS_MISSING, "permanent"))
        self.assertFalse(DeliveryRateState.objects.filter(channel="sms_send").exists())

    def test_a_given_admission_is_used_and_released_when_the_send_cannot_start(self):
        sender = sms_send.resolve_sender()
        admission = sms_send.admit_text(sender, "Hello")
        with (
            patch("apps.core.services.aws.sms_send.resolve_aws_credentials", side_effect=sms_send.AwsCredentialsError),
            self.assertRaises(sms_send.SmsDeliveryError),
        ):
            sms_send.send_text_message("+12095550101", "Hello", sender=sender, admission=admission)

        self.assertTrue(admission.settled)
        self.assertIsNone(self.state().tat)


class ActiveSmsTargetTests(TestCase):
    def setUp(self):
        cache.clear()
        clear_gate_cache()
        self.addCleanup(clear_gate_cache)

    def configure(self, number=NUMBER):
        return AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region=REGION,
            sms_from_number=number,
        )

    def test_the_configured_number_is_the_identity_in_use(self):
        self.assertIsNone(sms_send.active_rate_target())
        self.configure()

        self.assertEqual(rates.active_target(rates.Family.SMS), rates.Target("sms_send", IDENTITY))

    @patch("apps.core.services.aws.sms.boto3.client")
    def test_an_auto_detected_number_counts_once_cached_and_aws_is_never_called(self, boto_client):
        self.configure(number="")
        self.assertIsNone(sms_send.active_rate_target())

        cache.set(_cache_key(REGION), "+18005550000")

        self.assertEqual(sms_send.active_rate_target(), ("sms_send", f"{REGION}:+18005550000"))
        boto_client.assert_not_called()

    def test_the_campaign_lane_is_gated_while_the_sms_identity_is_held(self):
        self.configure()
        now = FakeClock().now()
        DeliveryRateState.objects.create(
            channel="sms_send",
            identity=IDENTITY,
            cooldown_group=f"sms:{REGION}",
            bulk_gate_until=now + timedelta(minutes=5),
        )

        self.assertTrue(rates.lane_gated(rates.Family.SMS, rates.Lane.BULK, now=now))
        self.assertFalse(rates.lane_gated(rates.Family.SMS, rates.Lane.TRANSACTIONAL, now=now))
