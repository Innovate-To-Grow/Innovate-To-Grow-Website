"""DeliveryRatePolicy: seeded from DELIVERY_RATES, Smart rate on, the manual rate always kept, and documented limits
that can be lowered but never raised above their settings value."""

import copy
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet
from django.test import TestCase, override_settings

from apps.core.models import DeliveryRatePolicy
from apps.core.models.base.delivery_rates import CHANNEL_UNITS, MANUAL_RATE_HELP, SMART_RATE_HELP, display_number

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
