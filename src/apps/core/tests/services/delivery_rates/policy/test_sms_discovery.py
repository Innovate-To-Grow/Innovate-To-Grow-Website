from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from apps.core.models import DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.runtime import discovery
from apps.core.tests.services.delivery_rates.policy.test_discovery import (
    REGION,
    SES,
    SMS,
    SPEND,
    DiscoveryTestCase,
    number,
)

from ..helpers import START, Channel, set_policy


class SmsDiscoveryTests(DiscoveryTestCase):
    def test_the_numbers_rate_type_and_the_spend_limit_are_read(self):
        stubber = self.stub("pinpoint-sms-voice-v2")
        stubber.add_response("describe_phone_numbers", {"PhoneNumbers": [number("+15550199", 1)], "NextToken": "n"})
        stubber.add_response("describe_phone_numbers", {"PhoneNumbers": [number()]}, {"NextToken": "n"})
        stubber.add_response("describe_spend_limits", SPEND)

        rates.refresh_discovery(Channel.SMS_SEND, SMS)

        state = DeliveryRateState.objects.get(identity=SMS)
        self.assertEqual(state.discovered_parts_rate, 3.0)
        self.assertEqual(state.discovered_extra["number_type"], "TOLL_FREE")
        self.assertEqual(state.discovered_extra["spend_limit"], 100)
        self.assertEqual(state.cooldown_group, f"sms:{REGION}")

    def test_a_refused_spend_limit_read_keeps_the_number_limits_and_warns(self):
        stubber = self.stub("pinpoint-sms-voice-v2")
        stubber.add_response("describe_phone_numbers", {"PhoneNumbers": [number()]})
        stubber.add_client_error("describe_spend_limits", "AccessDeniedException", http_status_code=403)

        rates.refresh_discovery(Channel.SMS_SEND, SMS)

        state = DeliveryRateState.objects.get(identity=SMS)
        self.assertEqual(state.discovered_parts_rate, 3.0)
        self.assertEqual(state.discovery_error, "AccessDeniedException: sms-voice:DescribeSpendLimits")

    def test_a_sender_id_is_read_with_describe_sender_ids(self):
        stubber = self.stub("pinpoint-sms-voice-v2")
        sender = {
            "SenderIdArn": f"arn:aws:sms-voice:{REGION}:123456789012:sender-id/I2G/US",
            "SenderId": "I2G",
            "IsoCountryCode": "US",
            "MessageTypes": ["TRANSACTIONAL"],
            "MonthlyLeasingPrice": "0",
            "DeletionProtectionEnabled": False,
            "Registered": True,
            "MessagingLimits": {"RateLimits": {"SMS": 10}},
        }
        stubber.add_response("describe_sender_ids", {"SenderIds": [sender]})
        stubber.add_response("describe_spend_limits", SPEND)

        rates.refresh_discovery(Channel.SMS_SEND, f"{REGION}:i2g")

        state = DeliveryRateState.objects.get(identity=f"{REGION}:i2g")
        self.assertEqual((state.discovered_parts_rate, state.discovered_extra["number_type"]), (10.0, "SENDER_ID"))

    def test_a_raised_spend_limit_lets_the_spend_breaker_probe_now(self):
        self.state(
            Channel.SMS_SEND,
            SMS,
            breaker_state="open",
            breaker_reason="spend_limit",
            breaker_retry_at=START + timedelta(hours=1),
            discovered_extra={"spend_limit": 50},
        )
        stubber = self.stub("pinpoint-sms-voice-v2")
        stubber.add_response("describe_phone_numbers", {"PhoneNumbers": [number()]})
        stubber.add_response("describe_spend_limits", SPEND)

        rates.refresh_discovery(Channel.SMS_SEND, SMS)

        self.assertEqual(DeliveryRateState.objects.get(identity=SMS).breaker_retry_at, START)


class GateTests(DiscoveryTestCase):
    def test_the_compare_and_set_gate_lets_one_of_two_callers_read(self):
        state = self.state()

        first = discovery._claim(state.pk, Channel.SES_SEND, START, force=False)
        second = discovery._claim(state.pk, Channel.SES_SEND, START, force=False)

        self.assertEqual((first, second), (True, False))

    def test_a_read_that_is_not_due_is_skipped(self):
        self.state(discovery_next_at=START + timedelta(minutes=5))
        self.stub("sesv2")  # no responses: a call would fail the test

        self.assertEqual(rates.refresh_discovery(Channel.SES_SEND, SES), 0)

    def test_channels_without_discovery_read_nothing(self):
        self.assertEqual(rates.refresh_discovery(Channel.GRAPH_SEND), 0)


class AdmissionDiscoveryTests(DiscoveryTestCase):
    def setUp(self):
        super().setUp()
        set_policy(Channel.SES_SEND, smart_enabled=False, manual_rate=Decimal(10))

    def test_a_due_read_starts_in_the_background_after_commit_and_the_send_never_waits(self):
        with (
            patch.object(discovery, "start_in_process_task") as start,
            patch.object(discovery, "read_ses_account", side_effect=AssertionError("read inline")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            rates.admit(Channel.SES_SEND, SES, budget_cost=1)
            rates.admit(Channel.SES_SEND, SES, budget_cost=1, max_wait=1)

        start.assert_called_once()
        self.assertEqual(start.call_args.args[1:], (Channel.SES_SEND, SES))
        self.assertTrue(start.call_args.kwargs["best_effort_start"])
        self.assertEqual(DeliveryRateState.objects.get(identity=SES).discovery_next_at, START + timedelta(hours=1))

    def test_a_throttle_brings_the_next_read_forward_but_not_closer_than_the_minimum_gap(self):
        self.state(discovered_at=START - timedelta(seconds=10), discovery_next_at=START + timedelta(hours=1))
        admission = rates.admit(Channel.SES_SEND, SES, budget_cost=1)

        rates.record(admission, rates.throttle(retry_after=1))

        self.assertEqual(DeliveryRateState.objects.get(identity=SES).discovery_next_at, START + timedelta(seconds=50))
