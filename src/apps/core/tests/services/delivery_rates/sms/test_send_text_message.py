from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import AWSCredentialConfig, DeliveryRateState, DeliveryUsageBucket
from apps.core.services import delivery_rates as rates
from apps.core.services.aws import sms_send
from apps.core.services.aws.sms import _cache_key
from apps.core.services.delivery_rates.lifecycle.families import clear_gate_cache
from apps.core.tests.services.delivery_rates.sms.test_sms_rate_control import (
    CLIENT,
    IDENTITY,
    NUMBER,
    REGION,
    SENT,
    add_error,
    stubbed_client,
)

from ..helpers import FakeClock


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
