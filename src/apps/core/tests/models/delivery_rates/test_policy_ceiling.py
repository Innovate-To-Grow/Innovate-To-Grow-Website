from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.core.models import DeliveryRatePolicy
from apps.core.tests.gmail_api_helpers import make_config
from apps.core.tests.models.delivery_rates.test_delivery_rate_policy import Channel, rates_with


class PolicyCeilingTests(TestCase):
    def setUp(self):
        cache.clear()
        DeliveryRatePolicy.objects.all().delete()

    def assert_field_error(self, policy, field, message):
        with self.assertRaises(ValidationError) as error:
            policy.full_clean()
        self.assertIn(field, error.exception.message_dict)
        self.assertIn(message, " ".join(error.exception.message_dict[field]))

    def test_documented_limits_can_be_lowered_but_not_raised(self):
        cases = (
            (
                Channel.GRAPH_SEND,
                "provider_limit",
                Decimal(31),
                Decimal(20),
                "The documented limit is 30 messages/min.",
            ),
            (Channel.GRAPH_SEND, "daily_limit", 10_001, 5_000, "10,000 recipients per 24 h"),
            (Channel.GRAPH_SEND, "hourly_external_limit", 501, 100, "500 external recipients per hour"),
            (Channel.GRAPH_SEND, "hourly_internal_limit", 1_001, 100, "1,000 internal recipients per hour"),
            (Channel.GRAPH_READ, "provider_limit", Decimal(1_001), Decimal(100), "1,000 requests/min"),
            (Channel.GMAIL_API_SEND, "provider_limit", Decimal(61), Decimal(30), "60 messages/min"),
            (Channel.GMAIL_API_SEND, "daily_message_limit", 2_001, 1_000, "2,000 messages per 24 h"),
            (Channel.GMAIL_API_SEND, "daily_limit", 3_001, 2_500, "3,000 recipients per 24 h"),
            (Channel.GMAIL_API_SEND, "daily_external_limit", 2_001, 500, "2,000 external recipients per 24 h"),
            (Channel.SMS_SEND, "provider_limit", Decimal(2), Decimal("0.5"), "1 messages/sec"),
        )
        for channel, field, too_high, lower, message in cases:
            with self.subTest(channel=channel, field=field):
                policy = DeliveryRatePolicy.for_channel(channel)
                setattr(policy, field, too_high)
                self.assert_field_error(policy, field, message)
                self.assert_field_error(policy, field, "It can be lowered here, not raised.")
                setattr(policy, field, lower)
                policy.manual_rate = min(policy.manual_rate, Decimal("0.5"))
                policy.save()
                policy.refresh_from_db()
                self.assertEqual(getattr(policy, field), lower)

    def test_a_raised_settings_value_raises_the_ceiling(self):
        policy = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        policy.provider_limit = Decimal(20)
        with self.assertRaises(ValidationError):
            policy.full_clean()
        with override_settings(DELIVERY_RATES=rates_with(Channel.SMS_SEND, provider_limit=20)):
            policy.full_clean()

    def test_limits_the_provider_reports_have_no_settings_ceiling(self):
        ses = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        ses.provider_limit = Decimal(500)
        ses.daily_limit = 1_000_000
        ses.full_clean()
        sms = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        sms.parts_limit = Decimal(100)
        sms.daily_limit = 50_000
        sms.full_clean()

    def test_parts_of_a_daily_limit_cannot_exceed_it(self):
        graph = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        graph.daily_limit = 400
        self.assert_field_error(graph, "hourly_external_limit", "It cannot be above the daily limit of 400 recipients.")
        self.assert_field_error(graph, "hourly_internal_limit", "daily limit of 400 recipients")
        gmail = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        gmail.daily_limit = None  # blank: the documented 3,000 applies
        gmail.daily_external_limit = 2_000
        gmail.full_clean()
        gmail.daily_limit = 1_500
        self.assert_field_error(gmail, "daily_external_limit", "daily limit of 1,500 recipients")

    def test_limits_a_channel_does_not_have_must_stay_empty(self):
        cases = (
            (Channel.GRAPH_SEND, "parts_limit", Decimal(3)),
            (Channel.SES_SEND, "hourly_external_limit", 10),
            (Channel.SES_SEND, "limits_confirmed", True),
            (Channel.SMS_SEND, "internal_domain", "ucmerced.edu"),
            (Channel.SMTP_SEND, "daily_external_limit", 10),
            (Channel.GRAPH_READ, "daily_limit", 10),
            (Channel.GRAPH_READ, "budget_headroom", Decimal("0.5")),
            (Channel.GMAIL_IMAP, "transactional_reserve", Decimal("0.5")),
        )
        for channel, field, value in cases:
            with self.subTest(channel=channel, field=field):
                policy = DeliveryRatePolicy.for_channel(channel)
                setattr(policy, field, value)
                self.assert_field_error(policy, field, "has no such limit; leave it empty.")

    def test_internal_domain_is_normalized_and_validated(self):
        make_config(subjects=("i2g@g.ucmerced.edu",), active=False)
        gmail = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        gmail.internal_domain = "  UCMerced.EDU "
        gmail.full_clean()
        self.assertEqual(gmail.internal_domain, "ucmerced.edu")
        gmail.internal_domain = "not a domain"
        self.assert_field_error(gmail, "internal_domain", "domain")

    def test_only_an_allow_listed_account_domain_or_its_parent_can_be_internal(self):
        # Recipients in the internal domain skip Google's 2,000 external recipients a day, so naming any other
        # domain (gmail.com, a bare TLD) would raise that documented limit.
        make_config(subjects=("i2g@g.ucmerced.edu",), active=False)
        gmail = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        for allowed in ("g.ucmerced.edu", "ucmerced.edu", ""):
            with self.subTest(allowed=allowed):
                gmail.internal_domain = allowed
                gmail.full_clean()
        for refused in ("gmail.com", "merced.edu", "x.g.ucmerced.edu"):
            with self.subTest(refused=refused):
                gmail.internal_domain = refused
                self.assert_field_error(gmail, "internal_domain", "g.ucmerced.edu, ucmerced.edu")
        # A bare top-level domain is never a parent domain the list offers (and is no valid domain name either).
        gmail.internal_domain = "edu"
        self.assert_field_error(gmail, "internal_domain", "")

    def test_without_an_allow_list_only_the_settings_seed_can_be_internal(self):
        gmail = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        gmail.internal_domain = "ucmerced.edu"
        self.assert_field_error(gmail, "internal_domain", "No account is on a Gmail API allow-list yet")
        with override_settings(DELIVERY_RATES=rates_with(Channel.GMAIL_API_SEND, internal_domain="ucmerced.edu")):
            gmail.full_clean()

    def test_shares_are_bounded(self):
        gmail = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        for field, bad in (
            ("budget_headroom", Decimal(0)),
            ("budget_headroom", Decimal("1.5")),
            ("transactional_reserve", Decimal(1)),
        ):
            with self.subTest(field=field, value=bad):
                setattr(gmail, field, bad)
                with self.assertRaises(ValidationError) as error:
                    gmail.full_clean()
                self.assertIn(field, error.exception.message_dict)
                gmail.refresh_from_db()
        gmail.transactional_reserve = Decimal(0)
        gmail.budget_headroom = Decimal(1)
        gmail.full_clean()
        gmail.transactional_reserve = None  # blank: the lanes default applies
        gmail.full_clean()

    def test_the_channel_must_be_known_and_unique(self):
        DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        duplicate = DeliveryRatePolicy(**DeliveryRatePolicy.seed_values(Channel.SES_SEND), channel=Channel.SES_SEND)
        with self.assertRaises(ValidationError) as error:
            duplicate.full_clean()
        self.assertIn("channel", error.exception.message_dict)
        unknown = DeliveryRatePolicy(channel="fax_send", manual_rate=Decimal(1))
        with self.assertRaises(ValidationError) as error:
            unknown.full_clean()
        self.assertIn("channel", error.exception.message_dict)
