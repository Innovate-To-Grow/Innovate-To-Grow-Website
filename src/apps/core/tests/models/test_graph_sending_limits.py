"""The sending limits on a Microsoft Graph configuration: seeded from DELIVERY_RATES, validated to fit together, and
the migration step that hands the Graph policy row's seeded ceilings over to them."""

from decimal import Decimal
from importlib import import_module

from django.apps import apps as live_apps
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.models import DeliveryRatePolicy, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import SENDING_LIMIT_FIELDS
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, create_graph_config


class SendingLimitDefaultTests(SimpleTestCase):
    def test_the_defaults_are_the_graph_send_seeds(self):
        config = MicrosoftGraphProviderConfig()

        self.assertEqual(config.max_recipients_per_message, 500)
        self.assertEqual(config.messages_per_minute_limit, 30)
        self.assertEqual(config.recipients_per_day_limit, 10_000)
        self.assertEqual(config.external_recipients_per_hour_limit, 500)
        self.assertEqual(config.internal_recipients_per_hour_limit, 1_000)

    def test_the_defaults_follow_the_settings_not_a_constant(self):
        from django.conf import settings

        seeds = {**settings.DELIVERY_RATES["channels"]["graph_send"], "provider_limit": 45, "daily_limit": 20_000}
        channels = {**settings.DELIVERY_RATES["channels"], "graph_send": seeds}
        with override_settings(DELIVERY_RATES={**settings.DELIVERY_RATES, "channels": channels}):
            config = MicrosoftGraphProviderConfig()

        self.assertEqual((config.messages_per_minute_limit, config.recipients_per_day_limit), (45, 20_000))

    def test_every_limit_field_is_editable(self):
        for name in SENDING_LIMIT_FIELDS:
            with self.subTest(field=name):
                self.assertTrue(MicrosoftGraphProviderConfig._meta.get_field(name).editable)


class SendingLimitValidationTests(TestCase):
    def config(self, **values):
        return MicrosoftGraphProviderConfig(name="Graph", tenant_id=TENANT_ID, client_id=CLIENT_ID, **values)

    def test_limits_must_be_at_least_one(self):
        for name in SENDING_LIMIT_FIELDS:
            with self.subTest(field=name), self.assertRaises(ValidationError) as error:
                self.config(**{name: 0}).full_clean()
            self.assertIn(name, error.exception.message_dict)

    def test_no_message_and_no_hour_may_exceed_the_day(self):
        config = self.config(
            recipients_per_day_limit=1_000,
            max_recipients_per_message=1_001,
            external_recipients_per_hour_limit=1_001,
            internal_recipients_per_hour_limit=1_000,
        )

        with self.assertRaises(ValidationError) as error:
            config.full_clean()

        errors = error.exception.message_dict
        self.assertEqual(
            errors["max_recipients_per_message"],
            ["One message cannot have more recipients than the day's limit allows."],
        )
        self.assertEqual(
            errors["external_recipients_per_hour_limit"],
            ["An hourly limit cannot be above the recipients per day limit."],
        )
        self.assertNotIn("internal_recipients_per_hour_limit", errors)

    def test_blank_hourly_limits_mean_no_hourly_limit(self):
        config = create_graph_config(
            external_recipients_per_hour_limit=None, internal_recipients_per_hour_limit=None, certificate=False
        )

        config.refresh_from_db()
        self.assertIsNone(config.external_recipients_per_hour_limit)
        self.assertIsNone(config.internal_recipients_per_hour_limit)


class SeededCeilingHandoverTests(TestCase):
    """Migration 0043 blanks the Graph policy row's ceilings that still hold the documented seeds, so the values on
    the configuration apply; a limit the operator lowered is theirs and stays."""

    def migrate(self):
        module = import_module("apps.core.migrations.0043_graph_sending_limits")
        module.blank_seeded_graph_ceilings(live_apps, None)

    def seeded_policy(self, **values):
        """The Graph policy row as migration 0036 left it in production (the test database has already run 0043)."""
        policy = DeliveryRatePolicy.for_channel(DeliveryRatePolicy.Channel.GRAPH_SEND)
        for field, value in {
            "provider_limit": Decimal(30),
            "daily_limit": 10_000,
            "hourly_external_limit": 500,
            "hourly_internal_limit": 1_000,
            **values,
        }.items():
            setattr(policy, field, value)
        policy.save()
        return policy

    def test_seeded_values_are_blanked(self):
        policy = self.seeded_policy()

        self.migrate()

        policy.refresh_from_db()
        self.assertIsNone(policy.provider_limit)
        self.assertIsNone(policy.daily_limit)
        self.assertIsNone(policy.hourly_external_limit)
        self.assertIsNone(policy.hourly_internal_limit)
        self.assertEqual((policy.smart_enabled, policy.manual_rate), (True, Decimal("24.000")))

    def test_lowered_values_are_kept_and_other_channels_untouched(self):
        policy = self.seeded_policy(provider_limit=Decimal(25), hourly_external_limit=200)
        ses = DeliveryRatePolicy.for_channel(DeliveryRatePolicy.Channel.SES_SEND)

        self.migrate()

        policy.refresh_from_db()
        self.assertEqual((policy.provider_limit, policy.hourly_external_limit), (Decimal("25.000"), 200))
        self.assertIsNone(policy.daily_limit)  # still the seed, so handed over
        self.assertEqual(DeliveryRatePolicy.objects.get(pk=ses.pk).provider_limit, ses.provider_limit)

    def test_without_a_policy_row_nothing_happens(self):
        DeliveryRatePolicy.objects.filter(channel=DeliveryRatePolicy.Channel.GRAPH_SEND).delete()

        self.migrate()

        self.assertFalse(DeliveryRatePolicy.objects.filter(channel=DeliveryRatePolicy.Channel.GRAPH_SEND).exists())
