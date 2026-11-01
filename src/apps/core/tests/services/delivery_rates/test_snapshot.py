"""Status lines (Mail → Delivery Rates, the dashboard, send estimates) and the config-save receivers."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models.signals import post_save
from django.test import TestCase

from apps.core.models import DeliveryRateState, MicrosoftGraphProviderConfig
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates import receivers

from .helpers import START, Channel, FakeClock, set_policy

MAILBOX = "i2g@example.edu"
SES = "1:us-west-2"


def state(channel, identity, **values):
    group = rates.cooldown_group(channel, identity)
    return DeliveryRateState.objects.create(channel=channel, identity=identity, cooldown_group=group, **values)


def lines(channel):
    return rates.channel_status(channel, now=START).identities[0].lines


class StatusLineTests(TestCase):
    def setUp(self):
        cache.clear()
        FakeClock().install(self)

    def test_every_channel_has_a_status_before_it_ever_sends(self):
        statuses = rates.snapshot(now=START)

        self.assertEqual([status.channel for status in statuses], list(Channel.values))
        for status in statuses:
            with self.subTest(channel=status.channel):
                self.assertTrue(status.headline.startswith("Now: "), status.headline)
                self.assertIn(status.unit, status.headline)
                self.assertTrue(status.smart_enabled)

    def test_graph_smart_rate_with_its_documented_limits_and_budgets(self):
        self.assertEqual(
            lines(Channel.GRAPH_SEND),
            (
                "Now: 24 messages/min · Smart · 80% of the 30 messages/min limit (documented)",
                "Provider limit: 30 messages/min (documented)",
                "Last 24 h: 0 / 10,000 recipients (campaigns stop at 900)",
                "Last hour: 0 / 500 external recipients (campaigns stop at 450)",
                "Last hour: 0 / 1,000 internal recipients (campaigns stop at 900)",
            ),
        )

    def test_gmail_api_budgets_show_the_headroom(self):
        self.assertIn(
            "Last 24 h: 0 / 2,000 messages (all mail stops at 1,800, campaigns at 1,350)", lines(Channel.GMAIL_API_SEND)
        )

    def test_manual_rate_shows_what_smart_rate_would_use(self):
        set_policy(Channel.GRAPH_SEND, smart_enabled=False, manual_rate=Decimal(10))

        self.assertEqual(lines(Channel.GRAPH_SEND)[0], "Now: 10 messages/min · Manual (Smart rate would use 24)")

    def test_a_manual_rate_above_the_reported_limit_is_shown_capped(self):
        set_policy(Channel.SES_SEND, smart_enabled=False, manual_rate=Decimal(20))
        state(Channel.SES_SEND, SES, discovered_rate=14.0, discovered_at=START - timedelta(minutes=3))

        status = lines(Channel.SES_SEND)

        self.assertEqual(status[0], "Now: 14 recipients/sec · Manual · capped to the 14 recipients/sec AWS reports")
        self.assertEqual(status[1], "Provider limit: 14 recipients/sec (reported by AWS 3 min ago)")

    def test_a_cooldown_and_a_breaker_replace_the_rate(self):
        state(Channel.GRAPH_SEND, MAILBOX, cooldown_until=START + timedelta(seconds=20), cooldown_reason="throttled")
        state(
            Channel.SES_SEND,
            SES,
            breaker_state="open",
            breaker_scope="all",
            breaker_reason="account_paused",
            breaker_retry_at=START + timedelta(minutes=15),
        )

        self.assertEqual(lines(Channel.GRAPH_SEND)[0], "Paused until 12:00:20 UTC: Microsoft Graph asked to slow down")
        self.assertEqual(
            lines(Channel.SES_SEND)[0],
            "Stopped: AWS reports sending is paused for this account (next check 12:15:00 UTC)",
        )

    def test_recovering_smart_rate_shows_when_full_speed_returns(self):
        state(
            Channel.GRAPH_SEND,
            MAILBOX,
            mode="smart",
            factor_base=0.5,
            factor_changed_at=START,
            last_cut_at=START,
        )

        self.assertEqual(
            lines(Channel.GRAPH_SEND)[0],
            "Now: 12 messages/min · Smart · recovering after Microsoft Graph pushed back at 12:00 UTC "
            "(full speed about 12:50 UTC)",
        )

    def test_an_unknown_limit_says_smart_rate_starts_from_the_app_default(self):
        status = lines(Channel.SMTP_SEND)

        self.assertEqual(
            status[0],
            "Now: 27 messages/min · Smart · provider limit unknown, so it starts from the 60 messages/min app default",
        )
        self.assertTrue(status[1].startswith("Provider limit: 60 messages/min (unknown"))

    def test_sms_shows_the_message_parts_limit(self):
        state(Channel.SMS_SEND, "us-west-2:+15550100", discovered_parts_rate=3.0, discovered_at=START)

        self.assertIn("Message parts: 3 parts/sec (reported by AWS SMS)", lines(Channel.SMS_SEND))

    def test_an_advanced_limit_above_the_reported_one_is_flagged(self):
        set_policy(Channel.SES_SEND, provider_limit=Decimal(20), manual_rate=Decimal(10))
        state(Channel.SES_SEND, SES, discovered_rate=14.0, discovered_at=START)

        warnings = rates.channel_status(Channel.SES_SEND, now=START).identities[0].warnings

        self.assertIn(
            "The provider limit set under Advanced (20 recipients/sec) is above the 14 recipients/sec AWS "
            "reports; 14 applies.",
            warnings,
        )


class ReceiverTests(TestCase):
    def setUp(self):
        cache.clear()
        FakeClock().install(self)

    def test_every_config_model_is_connected(self):
        for label in receivers.CONFIG_CHANNELS:
            with self.subTest(label=label):
                from django.apps import apps

                self.assertTrue(post_save.has_listeners(apps.get_model(label)))

    def test_a_graph_config_save_half_opens_graph_permission_breakers_only(self):
        stopped = {
            "breaker_state": "open",
            "breaker_scope": "all",
            "breaker_reason": "permission",
            "breaker_retry_at": START + timedelta(hours=1),
        }
        send = state(Channel.GRAPH_SEND, MAILBOX, **stopped)
        read = state(Channel.GRAPH_READ, MAILBOX, **stopped)
        ses = state(Channel.SES_SEND, SES, **stopped)

        with self.captureOnCommitCallbacks(execute=True):
            receivers._saved(MicrosoftGraphProviderConfig, None)

        for row, retry in ((send, START), (read, START), (ses, START + timedelta(hours=1))):
            row.refresh_from_db()
            self.assertEqual(row.breaker_retry_at, retry)

    def test_fixture_loading_is_ignored(self):
        with self.captureOnCommitCallbacks() as callbacks:
            receivers._saved(MicrosoftGraphProviderConfig, None, raw=True)

        self.assertEqual(callbacks, [])

    def test_a_later_config_model_can_register_its_channels(self):
        self.addCleanup(receivers.CONFIG_CHANNELS.pop, "core.LegacyAccessGrant", None)

        receivers.register_config_channels("core.LegacyAccessGrant", [Channel.GMAIL_API_SEND])

        self.assertEqual(receivers.CONFIG_CHANNELS["core.LegacyAccessGrant"], (Channel.GMAIL_API_SEND,))
