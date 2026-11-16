from datetime import timedelta
from decimal import Decimal

from apps.core.models import DeliveryRatePolicy, DeliveryRateState, DeliveryUsageBucket
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.runtime import budget
from apps.core.tests.services.delivery_rates.engine.test_budget import SES, BudgetTestCase

from ..helpers import START, Channel, set_policy


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
