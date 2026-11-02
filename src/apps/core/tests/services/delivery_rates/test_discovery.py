"""Provider limit discovery against stubbed AWS clients: the SES and SMS mappings, failures that keep the last-known
limits, the compare-and-set gate, and admissions that start a due read in the background without waiting for it."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import boto3
from botocore.stub import Stubber
from django.core.cache import cache
from django.test import TestCase

from apps.core.models import DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.aws import quotas
from apps.core.services.aws.credentials import AwsCredentials
from apps.core.services.delivery_rates.runtime import discovery

from .helpers import START, Channel, FakeClock, set_policy

REGION = "us-west-2"
SES = f"7:{REGION}"
NUMBER = "+15550100"
SMS = f"{REGION}:{NUMBER}"
CREDS = AwsCredentials(access_key_id="test-access-key", secret_access_key="test-secret-key", region=REGION)


def account(**overrides):
    response = {
        "SendQuota": {"Max24HourSend": 50_000.0, "MaxSendRate": 14.0, "SentLast24Hours": 1_200.0},
        "SendingEnabled": True,
        "EnforcementStatus": "HEALTHY",
        "ProductionAccessEnabled": True,
        "DedicatedIpAutoWarmupEnabled": False,
    }
    return response | overrides


def number(phone=NUMBER, rate=3, number_type="TOLL_FREE"):
    return {
        "PhoneNumberArn": f"arn:aws:sms-voice:{REGION}:123456789012:phone-number/phone-{phone[-4:]}",
        "PhoneNumberId": f"phone-{phone[-4:]}",
        "PhoneNumber": phone,
        "Status": "ACTIVE",
        "IsoCountryCode": "US",
        "MessageType": "TRANSACTIONAL",
        "NumberCapabilities": ["SMS"],
        "NumberType": number_type,
        "MonthlyLeasingPrice": "2.00",
        "TwoWayEnabled": False,
        "SelfManagedOptOutsEnabled": False,
        "OptOutListName": "Default",
        "DeletionProtectionEnabled": False,
        "MessagingLimits": {"RateLimits": {"SMS": rate}},
        "CreatedTimestamp": START,
    }


SPEND = {
    "SpendLimits": [
        {"Name": "TEXT_MESSAGE_MONTHLY_SPEND_LIMIT", "EnforcedLimit": 100, "MaxLimit": 1_000, "Overridden": True}
    ]
}


class DiscoveryTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)
        self.clients = {}
        self.configs = []
        patcher = patch.object(quotas.boto3, "client", side_effect=self.aws_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        for target, value in (
            ("resolve_aws_credentials", lambda *args, **kwargs: CREDS),
            ("AWSCredentialConfig", SimpleNamespace(load=lambda: SimpleNamespace(pk=7))),
        ):
            patcher = patch.object(discovery, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def stub(self, service):
        # A session of its own: the patched boto3.client is what the code under test calls.
        session = boto3.session.Session(aws_access_key_id="x", aws_secret_access_key="y", region_name=REGION)
        client = session.client(service)
        stubber = Stubber(client)
        stubber.activate()
        self.addCleanup(stubber.deactivate)
        self.clients[service] = client
        return stubber

    def aws_client(self, service, **options):
        self.configs.append(options["config"])
        return self.clients[service]

    def state(self, channel=Channel.SES_SEND, identity=SES, **values):
        group = rates.cooldown_group(channel, identity)
        return DeliveryRateState.objects.create(channel=channel, identity=identity, cooldown_group=group, **values)


class SesDiscoveryTests(DiscoveryTestCase):
    def test_get_account_is_mapped_onto_the_state(self):
        self.stub("sesv2").add_response("get_account", account())

        self.assertEqual(rates.refresh_discovery(Channel.SES_SEND, SES), 1)

        state = DeliveryRateState.objects.get(identity=SES)
        self.assertEqual(
            (state.discovered_rate, state.discovered_daily, state.discovered_used_24h), (14.0, 50_000, 1_200)
        )
        self.assertEqual(state.discovered_extra["enforcement_status"], "HEALTHY")
        self.assertEqual((state.discovered_at, state.discovery_error), (START, ""))
        self.assertEqual(state.discovery_next_at, START + timedelta(hours=1))

    def test_one_attempt_with_the_settings_timeout(self):
        self.stub("sesv2").add_response("get_account", account())

        rates.refresh_discovery(Channel.SES_SEND, SES)

        config = self.configs[0]
        self.assertEqual((config.connect_timeout, config.read_timeout), (5, 5))
        self.assertEqual(config.retries["total_max_attempts"], 1)

    def test_an_unlimited_daily_quota_is_no_daily_limit(self):
        self.stub("sesv2").add_response("get_account", account(SendQuota={"Max24HourSend": -1.0, "MaxSendRate": 50.0}))

        rates.refresh_discovery(Channel.SES_SEND, SES)

        state = DeliveryRateState.objects.get(identity=SES)
        self.assertIsNone(state.discovered_daily)
        self.assertEqual(state.discovered_extra["max_24_hour_send"], -1.0)

    def test_sending_disabled_opens_the_breaker_and_enabled_closes_it(self):
        stubber = self.stub("sesv2")
        stubber.add_response("get_account", account(SendingEnabled=False))
        stubber.add_response("get_account", account())

        rates.refresh_discovery(Channel.SES_SEND, SES)
        state = DeliveryRateState.objects.get(identity=SES)
        self.assertEqual((state.breaker_state, state.breaker_reason), ("open", "account_paused"))

        rates.refresh_discovery(Channel.SES_SEND, SES, force=True)
        self.assertEqual(DeliveryRateState.objects.get(identity=SES).breaker_state, "closed")

    def test_access_denied_on_get_account_falls_back_to_get_send_quota(self):
        self.stub("sesv2").add_client_error("get_account", "AccessDeniedException", http_status_code=403)
        self.stub("ses").add_response(
            "get_send_quota", {"Max24HourSend": 200.0, "MaxSendRate": 1.0, "SentLast24Hours": 3.0}
        )

        rates.refresh_discovery(Channel.SES_SEND, SES)

        state = DeliveryRateState.objects.get(identity=SES)
        self.assertEqual(
            (state.discovered_rate, state.discovered_daily, state.discovered_extra["api"]), (1.0, 200, "ses")
        )

    def test_access_denied_keeps_the_last_known_limits_and_shows_the_error(self):
        self.state(discovered_rate=14.0, discovered_daily=50_000, discovered_at=START - timedelta(hours=26))
        self.stub("sesv2").add_client_error("get_account", "AccessDeniedException", http_status_code=403)
        self.stub("ses").add_client_error("get_send_quota", "AccessDenied", http_status_code=403)

        rates.refresh_discovery(Channel.SES_SEND, SES)

        state = DeliveryRateState.objects.get(identity=SES)
        self.assertEqual((state.discovered_rate, state.discovered_daily), (14.0, 50_000))
        self.assertEqual(state.discovered_at, START - timedelta(hours=26))
        self.assertEqual(state.discovery_error, "AccessDeniedException: ses:GetAccount; AccessDenied: ses:GetSendQuota")
        warning = rates.channel_status(Channel.SES_SEND, now=START).identities[0].warnings[0]
        self.assertIn("last read 26 h ago", warning)
        self.assertIn("using the last known 14", warning)

    def test_an_identity_that_is_not_the_active_account_is_not_read(self):
        self.stub("sesv2")

        rates.refresh_discovery(Channel.SES_SEND, "8:eu-west-1")

        self.assertEqual(
            DeliveryRateState.objects.get(identity="8:eu-west-1").discovery_error, "not the active AWS account"
        )

    def test_an_unexpected_failure_is_contained(self):
        with patch.object(discovery, "read_ses_account", side_effect=KeyError("x")), self.assertLogs(discovery.logger):
            rates.refresh_discovery(Channel.SES_SEND, SES)

        self.assertEqual(DeliveryRateState.objects.get(identity=SES).discovery_error, "unexpected error")


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
