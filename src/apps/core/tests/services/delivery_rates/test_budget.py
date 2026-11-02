"""Daily and hourly budgets: exact window boundaries, the transactional reserve, Graph's hourly and unconfirmed
limits, the Gmail API's message, recipient and external limits with headroom, SES's reported usage, SMTP host
profiles, and which answers give usage back."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.models import DeliveryRatePolicy, DeliveryRateState, DeliveryUsageBucket
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.runtime import budget

from .helpers import START, Channel, FakeClock, rates_with, set_policy

MAILBOX = "i2g@example.edu"
SES = "1:us-west-2"


class BudgetTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)

    def send(self, channel=Channel.GRAPH_SEND, identity=MAILBOX, *, recipients=1, external=0, lane="transactional"):
        return rates.admit(
            channel,
            identity,
            lane=lane,
            budget_cost=recipients,
            external_cost=external,
            message_cost=1,
            max_wait=86_400,
        )

    def usage(self, channel=Channel.GRAPH_SEND, identity=MAILBOX):
        state = DeliveryRateState.objects.get(channel=channel, identity=identity)
        return budget.usage(state, self.clock.now())


class DailyWindowTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        set_policy(
            Channel.GRAPH_SEND,
            daily_limit=10,
            hourly_external_limit=None,
            hourly_internal_limit=None,
            smart_enabled=False,
            manual_rate=Decimal(30),
        )

    def test_usage_ages_out_exactly_24_hours_after_its_bucket_ends(self):
        self.send(recipients=10)
        bucket_end = budget.bucket_start(START) + timedelta(seconds=budget.bucket_seconds())

        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(Channel.GRAPH_SEND, MAILBOX, budget_cost=1, max_wait=0)

        self.assertEqual(caught.exception.until, bucket_end + timedelta(hours=24))
        self.assertEqual(caught.exception.reason, "budget:daily_limit")
        self.clock.current = bucket_end + timedelta(hours=24) - timedelta(microseconds=1)
        with self.assertRaises(rates.RateDeferred):
            rates.admit(Channel.GRAPH_SEND, MAILBOX, budget_cost=1, max_wait=0)
        self.clock.current = bucket_end + timedelta(hours=24)
        self.assertIsNotNone(rates.admit(Channel.GRAPH_SEND, MAILBOX, budget_cost=1, max_wait=0))

    def test_campaigns_stop_at_the_reserve_while_transactional_mail_passes(self):
        # 10 a day, 10 % reserve: campaigns may use 9.
        self.send(recipients=8, lane="bulk")
        self.send(recipients=1, lane="bulk")
        with self.assertRaises(rates.RateDeferred):
            rates.admit(Channel.GRAPH_SEND, MAILBOX, lane="bulk", budget_cost=1, max_wait=0)

        self.assertIsNotNone(self.send(recipients=1))
        with self.assertRaises(rates.RateDeferred):
            rates.admit(Channel.GRAPH_SEND, MAILBOX, budget_cost=1, max_wait=0)

    def test_a_request_larger_than_the_whole_limit_is_refused(self):
        with self.assertRaises(rates.RateRefused):
            self.send(recipients=11)

    def test_usage_is_released_on_throttle_quota_breaker_none_and_release_but_kept_on_uncertain(self):
        cases = (
            (rates.throttle(retry_after=1), 0),
            (rates.quota("daily_quota"), 0),
            (rates.blocked("auth"), 0),
            (rates.none("bad_address"), 0),
            (rates.uncertain(), 3),
            (rates.ok(), 3),
        )
        for signal, kept in cases:
            with self.subTest(kind=signal.kind):
                DeliveryRateState.objects.all().delete()
                admission = self.send(recipients=3)
                rates.record(admission, signal)
                self.assertEqual(self.usage().day["total"], kept)
        DeliveryRateState.objects.all().delete()
        admission = self.send(recipients=3)
        rates.release(admission)
        self.assertEqual(self.usage().day["total"], 0)


class GraphLimitTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        set_policy(
            Channel.GRAPH_SEND,
            smart_enabled=False,
            manual_rate=Decimal(30),
            hourly_external_limit=5,
            hourly_internal_limit=8,
        )

    def test_external_and_internal_recipients_have_separate_hourly_windows(self):
        self.send(recipients=5, external=5)
        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(Channel.GRAPH_SEND, MAILBOX, budget_cost=1, external_cost=1, max_wait=0)
        self.assertEqual(caught.exception.reason, "budget:hourly_external_limit")

        self.assertIsNotNone(self.send(recipients=8))
        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(Channel.GRAPH_SEND, MAILBOX, budget_cost=1, max_wait=0)
        self.assertEqual(caught.exception.reason, "budget:hourly_internal_limit")

    def test_the_hourly_window_ends_an_hour_after_the_bucket(self):
        self.send(recipients=5, external=5)
        bucket_end = budget.bucket_start(START) + timedelta(seconds=budget.bucket_seconds())

        self.clock.current = bucket_end + timedelta(hours=1)

        self.assertIsNotNone(self.send(recipients=1, external=1))

    @override_settings(DELIVERY_RATES=rates_with(channels={"graph_send": {"unconfirmed_bulk_daily_limit": 20}}))
    def test_until_limits_are_confirmed_campaigns_stay_under_the_standard_preset(self):
        set_policy(Channel.GRAPH_SEND, hourly_internal_limit=None, daily_limit=None)
        self.send(recipients=8, lane="bulk")
        self.send(recipients=8, lane="bulk")
        with self.assertRaises(rates.RateDeferred):  # 20 × (1 − 0.1) = 18
            rates.admit(Channel.GRAPH_SEND, MAILBOX, lane="bulk", budget_cost=3, max_wait=0)

        set_policy(Channel.GRAPH_SEND, limits_confirmed=True)
        self.assertIsNotNone(self.send(recipients=3, lane="bulk"))


class GmailApiLimitTests(BudgetTestCase):
    SUBJECT = "i2g@example.edu"

    def setUp(self):
        super().setUp()
        set_policy(
            Channel.GMAIL_API_SEND,
            smart_enabled=False,
            manual_rate=Decimal(60),
            daily_limit=100,
            daily_external_limit=50,
            daily_message_limit=20,
        )

    def admit_gmail(self, **options):
        return self.send(Channel.GMAIL_API_SEND, self.SUBJECT, **options)

    def test_limits_apply_with_the_budget_headroom_and_the_channel_reserve(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        state = DeliveryRateState(channel=Channel.GMAIL_API_SEND, identity=self.SUBJECT, cooldown_group="")

        limits = {limit.name: limit for limit in budget.limits(policy, state)}

        self.assertEqual(policy.transactional_reserve, Decimal("0.250"))
        # 90 % headroom; campaigns also leave 25 % for transactional mail.
        self.assertEqual((limits["daily_limit"].usable, limits["daily_limit"].bulk_usable), (90, 67))
        self.assertEqual((limits["daily_external_limit"].usable, limits["daily_external_limit"].bulk_usable), (45, 33))
        self.assertEqual((limits["daily_message_limit"].usable, limits["daily_message_limit"].bulk_usable), (18, 13))

    def test_the_message_limit_stops_mail_before_the_recipient_limit(self):
        for _ in range(18):
            self.admit_gmail()

        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(Channel.GMAIL_API_SEND, self.SUBJECT, budget_cost=1, message_cost=1, max_wait=0)

        self.assertEqual(caught.exception.reason, "budget:daily_message_limit")

    def test_external_recipients_have_their_own_limit(self):
        self.admit_gmail(recipients=45, external=45)

        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(
                Channel.GMAIL_API_SEND, self.SUBJECT, budget_cost=1, external_cost=1, message_cost=1, max_wait=0
            )

        self.assertEqual(caught.exception.reason, "budget:daily_external_limit")
        self.assertIsNotNone(self.admit_gmail(recipients=1))


class ReportedUsageTests(BudgetTestCase):
    def test_ses_folds_in_what_aws_reported_sent_in_the_last_24_hours(self):
        state = DeliveryRateState.objects.create(
            channel=Channel.SES_SEND,
            identity=SES,
            cooldown_group="ses:us-west-2",
            discovered_daily=100,
            discovered_used_24h=95,
            discovered_at=START - timedelta(minutes=1),
            discovery_next_at=START + timedelta(hours=1),
        )
        set_policy(Channel.SES_SEND, smart_enabled=False, manual_rate=Decimal(10))
        self.send(Channel.SES_SEND, SES, recipients=4)

        self.assertEqual(budget.usage(state, START).day["total"], 99)
        with self.assertRaises(rates.RateDeferred) as caught:
            rates.admit(Channel.SES_SEND, SES, budget_cost=2, max_wait=0)
        # What AWS reported ages out on no bucket of ours: re-check after quota_recheck_seconds.
        self.assertEqual(caught.exception.until, START + timedelta(seconds=600))

    def test_an_old_report_is_not_folded_in(self):
        state = DeliveryRateState.objects.create(
            channel=Channel.SES_SEND,
            identity=SES,
            cooldown_group="ses:us-west-2",
            discovered_used_24h=95,
            discovered_at=START - timedelta(hours=25),
        )

        self.assertEqual(budget.usage(state, START).day["total"], 0)


class SmtpHostProfileTests(BudgetTestCase):
    def test_the_gmail_smtp_profile_limits_messages_per_day(self):
        policy = set_policy(Channel.SMTP_SEND, daily_message_limit=None)
        state = DeliveryRateState(channel=Channel.SMTP_SEND, identity="smtp.gmail.com:587:i2g@example.edu")

        limits = {limit.name: limit for limit in budget.limits(policy, state)}

        self.assertEqual((limits["daily_message_limit"].limit, limits["daily_message_limit"].source), (2_000, "host"))
        set_policy(Channel.SMTP_SEND, daily_message_limit=500)
        policy.refresh_from_db()
        limits = {limit.name: limit for limit in budget.limits(policy, state)}
        self.assertEqual((limits["daily_message_limit"].limit, limits["daily_message_limit"].source), (500, "operator"))

    def test_other_hosts_have_no_daily_limit(self):
        policy = set_policy(Channel.SMTP_SEND)
        state = DeliveryRateState(channel=Channel.SMTP_SEND, identity="smtp.example.edu:587:user")

        self.assertEqual(budget.limits(policy, state), [])


class PurgeTests(BudgetTestCase):
    def test_purge_deletes_buckets_older_than_the_retention(self):
        self.send(recipients=1)
        self.assertEqual(budget.purge(START + timedelta(hours=47)), 0)
        self.assertEqual(budget.purge(START + timedelta(hours=49)), 1)
        self.assertFalse(DeliveryUsageBucket.objects.exists())
