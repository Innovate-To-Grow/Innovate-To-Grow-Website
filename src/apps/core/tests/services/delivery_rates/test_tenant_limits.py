"""The Microsoft Graph mailbox limits entered on the active Graph configuration replace the documented ceilings of
``DELIVERY_RATES`` for the ``graph_send`` channel: in the rate, the budgets, the policy's ceilings and the status
lines. The seeds apply only while no active configuration exists."""

from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import DeliveryRatePolicy, DeliveryRateState
from apps.core.services.delivery_rates.rules import tenant
from apps.core.services.delivery_rates.rules.defaults import channel_settings, rate_spec
from apps.core.services.delivery_rates.rules.policy import BoundSource, effective_rate
from apps.core.services.delivery_rates.runtime import budget
from apps.core.services.delivery_rates.snapshot import identity_status
from apps.core.tests.graph_helpers import create_graph_config

from .helpers import Channel, FakeClock

MAILBOX = "i2g@example.edu"
OIT_LIMITS = {
    "messages_per_minute_limit": 40,
    "recipients_per_day_limit": 12_000,
    "external_recipients_per_hour_limit": None,
    "internal_recipients_per_hour_limit": 2_000,
    "max_recipients_per_message": 300,
}


def graph_config(**values):
    return create_graph_config(scope=(MAILBOX,), name="Graph", is_active=True, mailbox=MAILBOX, **values)


class TenantLimitsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)

    def state(self):
        return DeliveryRateState(channel=Channel.GRAPH_SEND, identity=MAILBOX, cooldown_group=f"graph:{MAILBOX}")

    def test_without_an_active_configuration_the_documented_seeds_apply(self):
        spec = channel_settings(Channel.GRAPH_SEND)

        self.assertEqual(
            (spec["provider_limit"], spec["daily_limit"], spec["max_recipients_per_message"]), (30, 10_000, 500)
        )
        self.assertFalse(tenant.from_tenant(spec))
        self.assertFalse(rate_spec(Channel.GRAPH_SEND).tenant_limits)
        self.assertEqual(tenant.configured_limits(Channel.GRAPH_SEND), {})

    def test_the_active_configuration_replaces_the_documented_limits(self):
        graph_config(**OIT_LIMITS)

        spec = channel_settings(Channel.GRAPH_SEND)

        self.assertTrue(tenant.from_tenant(spec))
        self.assertEqual(spec["provider_limit"], 40)
        self.assertEqual(spec["daily_limit"], 12_000)
        self.assertIsNone(spec["hourly_external_limit"])
        self.assertEqual(spec["hourly_internal_limit"], 2_000)
        self.assertEqual(spec["max_recipients_per_message"], 300)
        # The rest of the seed, and every other channel, is untouched.
        self.assertEqual(
            (spec["manual_rate"], spec["headroom"], spec["unconfirmed_bulk_daily_limit"]), (24, 0.8, 1_000)
        )
        self.assertFalse(tenant.from_tenant(channel_settings(Channel.SES_SEND)))
        self.assertEqual(tenant.configured_limits(Channel.GRAPH_READ), {})

    def test_an_inactive_configuration_is_ignored(self):
        create_graph_config(scope=(MAILBOX,), name="Standby", is_active=False, messages_per_minute_limit=5)

        self.assertEqual(channel_settings(Channel.GRAPH_SEND)["provider_limit"], 30)

    def test_smart_rate_and_the_status_line_follow_the_configured_messages_per_minute(self):
        graph_config(**OIT_LIMITS)
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        spec = rate_spec(Channel.GRAPH_SEND)

        rate = effective_rate(policy, self.state(), spec, self.clock.now())

        self.assertTrue(spec.tenant_limits)
        self.assertEqual((rate.bound.value, rate.bound.source), (40.0, BoundSource.TENANT))
        self.assertEqual(rate.rate, 32.0)  # 0.8 headroom of the mailbox's 40, not of the documented 30
        status = identity_status(policy, self.state(), self.clock.now())
        self.assertEqual(
            status.lines[0],
            "Now: 32 messages/min · Smart · 80% of the 40 messages/min limit "
            "(the mailbox limit on the Microsoft Graph configuration)",
        )
        self.assertEqual(
            status.lines[1], "Provider limit: 40 messages/min (the mailbox limit on the Microsoft Graph configuration)"
        )

    def test_the_budgets_follow_the_configured_day_and_hour_limits(self):
        graph_config(**OIT_LIMITS)
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)

        limits = {limit.name: limit for limit in budget.limits(policy, self.state())}

        self.assertEqual(limits["daily_limit"].limit, 12_000)
        self.assertEqual(limits["hourly_internal_limit"].limit, 2_000)
        self.assertNotIn("hourly_external_limit", limits)

    def test_a_fresh_policy_row_leaves_the_ceilings_blank_so_the_configuration_applies(self):
        graph_config(**OIT_LIMITS)

        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)

        self.assertIsNone(policy.provider_limit)
        self.assertIsNone(policy.daily_limit)
        self.assertIsNone(policy.hourly_internal_limit)
        self.assertEqual((policy.smart_enabled, policy.manual_rate), (True, Decimal("24.000")))

    def test_the_policy_ceilings_are_the_configured_limits(self):
        graph_config(**OIT_LIMITS)
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)

        policy.provider_limit = Decimal(40)
        policy.daily_limit = 12_000
        policy.full_clean()  # at the configured limits

        policy.provider_limit = Decimal(41)
        with self.assertRaises(ValidationError) as error:
            policy.full_clean()
        self.assertEqual(
            error.exception.message_dict["provider_limit"],
            ["The limit on the Microsoft Graph configuration is 40 messages/min. It can be lowered here, not raised."],
        )

        policy.provider_limit = Decimal(25)  # below it (and above the manual rate): the operator's own limit
        policy.full_clean()

    def test_lowering_the_configuration_caps_a_higher_stored_policy_limit(self):
        config = graph_config(**OIT_LIMITS)
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.provider_limit = Decimal(40)
        policy.save()
        config.messages_per_minute_limit = 25
        config.save()

        rate = effective_rate(policy, self.state(), rate_spec(Channel.GRAPH_SEND), self.clock.now())

        self.assertEqual((rate.bound.value, rate.bound.source), (25.0, BoundSource.TENANT))
