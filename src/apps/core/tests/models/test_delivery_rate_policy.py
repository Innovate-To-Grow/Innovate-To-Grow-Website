"""DeliveryRatePolicy: seeded from DELIVERY_RATES, Smart rate on, the manual rate always kept, and documented limits
that can be lowered but never raised above their settings value."""

import copy
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.test import TestCase, override_settings

from apps.core.models import DeliveryRatePolicy
from apps.core.models.base.delivery_rates import CHANNEL_UNITS, MANUAL_RATE_HELP, SMART_RATE_HELP, display_number
from apps.core.tests.gmail_api_helpers import make_config

Channel = DeliveryRatePolicy.Channel


def rates_with(channel, **values):
    rates = copy.deepcopy(settings.DELIVERY_RATES)
    rates["channels"][channel].update(values)
    return rates


class PolicySeedTests(TestCase):
    def setUp(self):
        cache.clear()
        # Migration 0036 seeds the rows; these tests start without them, as after a table flush.
        DeliveryRatePolicy.objects.all().delete()

    def test_for_channel_creates_every_channel_from_the_settings_with_smart_rate_on(self):
        for channel in Channel.values:
            with self.subTest(channel=channel):
                spec = settings.DELIVERY_RATES["channels"][channel]
                policy = DeliveryRatePolicy.for_channel(channel)

                self.assertTrue(policy.smart_enabled)
                self.assertEqual(policy.manual_rate, Decimal(str(spec["manual_rate"])))
                expected_limit = spec["provider_limit"]
                self.assertEqual(policy.provider_limit, None if expected_limit is None else Decimal(expected_limit))
                policy.full_clean()
        self.assertEqual(DeliveryRatePolicy.objects.count(), len(Channel.values))

    def test_channel_specific_seeds(self):
        graph = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        self.assertEqual(
            (graph.daily_limit, graph.hourly_external_limit, graph.hourly_internal_limit), (10_000, 500, 1_000)
        )
        self.assertFalse(graph.limits_confirmed)
        gmail = DeliveryRatePolicy.for_channel(Channel.GMAIL_API_SEND)
        self.assertEqual(
            (gmail.daily_message_limit, gmail.daily_limit, gmail.daily_external_limit), (2_000, 3_000, 2_000)
        )
        self.assertEqual((gmail.budget_headroom, gmail.transactional_reserve), (Decimal("0.900"), Decimal("0.250")))
        self.assertEqual(gmail.internal_domain, "")
        sms = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        self.assertIsNone(sms.parts_limit)
        read = DeliveryRatePolicy.for_channel(Channel.GRAPH_READ)
        self.assertIsNone(read.daily_limit)
        self.assertEqual(read.budget_headroom, Decimal(1))

    def test_for_channel_returns_the_existing_row_and_heals_a_deleted_one(self):
        first = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        first.manual_rate = Decimal("4.5")
        first.save()

        self.assertEqual(DeliveryRatePolicy.for_channel(Channel.SES_SEND).pk, first.pk)
        self.assertEqual(DeliveryRatePolicy.for_channel(Channel.SES_SEND).manual_rate, Decimal("4.500"))
        first.delete()
        healed = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        self.assertNotEqual(healed.pk, first.pk)
        self.assertEqual(healed.manual_rate, Decimal(10))

    def test_for_channel_returns_the_row_another_process_inserted_after_its_lookup(self):
        # Another process creates the row between this lookup and this insert, as concurrent OTP sends do.
        other = DeliveryRatePolicy.objects.create(
            channel=Channel.SMS_SEND, **DeliveryRatePolicy.seed_values("sms_send")
        )
        real_get = QuerySet.get
        calls = []

        def missing_once(queryset, *args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise DeliveryRatePolicy.DoesNotExist
            return real_get(queryset, *args, **kwargs)

        with patch.object(QuerySet, "get", missing_once):
            policy = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)

        self.assertEqual(policy.pk, other.pk)
        self.assertEqual(DeliveryRatePolicy.objects.filter(channel=Channel.SMS_SEND).count(), 1)

    def test_for_channel_refuses_an_unknown_channel(self):
        with self.assertRaisesMessage(ValueError, "Unknown delivery channel: 'fax_send'"):
            DeliveryRatePolicy.for_channel("fax_send")
        self.assertFalse(DeliveryRatePolicy.objects.exists())

    def test_seeds_follow_a_settings_override(self):
        with override_settings(DELIVERY_RATES=rates_with(Channel.SMS_SEND, provider_limit=20, manual_rate=3)):
            policy = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        self.assertEqual((policy.provider_limit, policy.manual_rate), (Decimal(20), Decimal(3)))

    def test_units_and_help_texts(self):
        self.assertEqual(set(CHANNEL_UNITS), set(Channel.values))
        self.assertEqual(CHANNEL_UNITS[Channel.SES_SEND].label, "recipients/sec")
        self.assertEqual(CHANNEL_UNITS[Channel.SMS_SEND].label, "messages/sec")
        self.assertEqual(CHANNEL_UNITS[Channel.GRAPH_SEND].per_seconds, 60)
        self.assertEqual(DeliveryRatePolicy._meta.get_field("smart_enabled").help_text, SMART_RATE_HELP)
        self.assertEqual(DeliveryRatePolicy._meta.get_field("manual_rate").help_text, MANUAL_RATE_HELP)
        self.assertIn("While Smart rate is on it takes priority over the manual rate;", SMART_RATE_HELP)
        self.assertEqual(str(DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)), "Email · Microsoft Graph: Smart rate")
        policy = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        policy.smart_enabled = False
        self.assertEqual(str(policy), "SMS · AWS End User Messaging: Manual 1.000 messages/sec")
        self.assertEqual(display_number(Decimal("10000.000")), "10,000")


class PolicyManualRateTests(TestCase):
    def setUp(self):
        cache.clear()
        DeliveryRatePolicy.objects.all().delete()

    def test_switching_smart_rate_keeps_the_manual_rate(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.manual_rate = Decimal("12.5")
        policy.save()
        for smart in (False, True, False, True):
            policy.smart_enabled = smart
            policy.save()
            policy.refresh_from_db()
            self.assertEqual(policy.manual_rate, Decimal("12.500"))

    def test_the_manual_rate_can_be_edited_while_smart_rate_is_on(self):
        policy = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        self.assertTrue(policy.smart_enabled)
        policy.manual_rate = Decimal("2.25")
        policy.save()
        policy.refresh_from_db()
        self.assertEqual((policy.smart_enabled, policy.manual_rate), (True, Decimal("2.250")))

    def test_the_manual_rate_cannot_exceed_the_provider_limit(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.manual_rate = Decimal("30.001")
        with self.assertRaises(ValidationError) as error:
            policy.full_clean()
        self.assertEqual(
            error.exception.message_dict["manual_rate"],
            ["It cannot be set above the provider limit of 30 messages/min (Advanced)."],
        )

        policy.manual_rate = Decimal(30)
        policy.provider_limit = Decimal(20)
        with self.assertRaisesMessage(ValidationError, "provider limit of 20 messages/min"):
            policy.full_clean()
        policy.provider_limit = None  # blank: the documented 30 applies
        policy.full_clean()

    def test_without_a_provider_limit_the_manual_rate_is_unbounded(self):
        smtp = DeliveryRatePolicy.for_channel(Channel.SMTP_SEND)
        smtp.manual_rate = Decimal(5_000)
        smtp.full_clean()
        ses = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        ses.manual_rate = Decimal(200)
        ses.full_clean()
        ses.provider_limit = Decimal(100)
        with self.assertRaisesMessage(ValidationError, "provider limit of 100 recipients/sec"):
            ses.full_clean()

    def test_the_slowest_rate_is_one_thousandth(self):
        policy = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        policy.manual_rate = Decimal("0.001")
        policy.full_clean()
        policy.manual_rate = Decimal(0)
        with self.assertRaises(ValidationError) as error:
            policy.full_clean()
        self.assertIn("manual_rate", error.exception.message_dict)

    def test_save_validates(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.manual_rate = Decimal(31)
        with self.assertRaises(ValidationError):
            policy.save()
        policy.refresh_from_db()
        self.assertEqual(policy.manual_rate, Decimal(24))


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
