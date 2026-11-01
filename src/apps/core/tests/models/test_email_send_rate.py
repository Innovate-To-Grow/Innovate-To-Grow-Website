"""EmailServiceConfig send-rate rules: the operator's cap, Microsoft Graph's own ceiling and inline batch limits."""

from unittest.mock import patch

from django.test import TestCase

from apps.core.models import EmailServiceConfig
from apps.core.tests.graph_helpers import create_graph_config

TENANT_ID = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def make_email(provider="ses", **overrides):
    values = {"name": "Mail", "is_active": True, "provider": provider, "from_email": "sender@example.com"}
    return EmailServiceConfig.objects.create(**values | overrides)


def make_graph(**overrides):
    values = {
        "name": "Graph",
        "is_active": True,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
    }
    return create_graph_config(**values | overrides)


class EffectiveSendRateTest(TestCase):
    def test_ses_and_smtp_use_the_operators_cap_as_is(self):
        for provider in ("ses", "smtp"):
            with self.subTest(provider):
                EmailServiceConfig.objects.all().delete()
                config = make_email(provider, max_send_rate=10)

                self.assertEqual(config.effective_send_rate, 10.0)
                self.assertEqual(config.send_rate_display, "10 emails/sec")

    def test_a_zero_cap_means_unlimited_for_ses(self):
        config = make_email(max_send_rate=0)

        self.assertEqual(config.effective_send_rate, 0.0)
        self.assertEqual(config.send_rate_display, "Unlimited")

    def test_graph_is_held_to_its_per_minute_ceiling_whatever_the_cap(self):
        make_graph(messages_per_minute=24)
        for cap in (1, 10, 100):
            with self.subTest(cap=cap):
                EmailServiceConfig.objects.all().delete()
                config = make_email("graph", max_send_rate=cap)

                self.assertAlmostEqual(config.effective_send_rate, 0.4)
                self.assertEqual(config.send_rate_display, "24 emails/min")

    def test_graph_is_never_unlimited(self):
        make_graph(messages_per_minute=30)
        config = make_email("graph", max_send_rate=0)

        self.assertAlmostEqual(config.effective_send_rate, 0.5)
        self.assertEqual(config.send_rate_display, "30 emails/min")

    def test_the_ceiling_follows_the_active_graph_config(self):
        make_graph(messages_per_minute=6)

        self.assertAlmostEqual(make_email("graph").effective_send_rate, 0.1)

    def test_graph_without_a_saved_config_uses_the_default_ceiling(self):
        config = make_email("graph", max_send_rate=0)

        self.assertAlmostEqual(config.effective_send_rate, 24 / 60)

    def test_rates_of_a_second_or_more_are_shown_per_second(self):
        config = make_email(max_send_rate=3)

        self.assertEqual(config.send_rate_display, "3 emails/sec")


class InlineSendLimitTest(TestCase):
    def test_only_graph_limits_inline_batches(self):
        self.assertEqual(make_email("graph").inline_send_limit, 20)
        for provider in ("ses", "smtp"):
            with self.subTest(provider):
                EmailServiceConfig.objects.all().delete()
                self.assertIsNone(make_email(provider).inline_send_limit)

    def test_the_default_config_has_no_inline_limit(self):
        self.assertIsNone(EmailServiceConfig().inline_send_limit)

    def test_the_limit_is_read_from_the_module_constant(self):
        config = make_email("graph")
        with patch("apps.core.models.base.service_credentials.email.GRAPH_INLINE_BATCH_LIMIT", 3):
            self.assertEqual(config.inline_send_limit, 3)
