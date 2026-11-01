"""Migrations 0036 and 0037: 0036 follows PR #643's 0035 and seeds one policy row per channel (Smart rate on
everywhere) while keeping the rates people set before; 0037 retires the old rate fields. Both reverse cleanly."""

import copy
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.core.models import DeliveryRatePolicy, EmailServiceConfig

GRAPH_CERTIFICATES = ("core", "0035_graph_certificate_and_mailbox_scope")
RATE_CONTROL = ("core", "0036_delivery_rate_control")
RETIRED_RATES = ("core", "0037_retire_old_send_rates")
RATE_TABLES = ("core_deliveryratepolicy", "core_deliveryratestate", "core_deliveryusagebucket")
migration = importlib.import_module("apps.core.migrations.0036_delivery_rate_control")
Channel = DeliveryRatePolicy.Channel


def seed():
    migration.seed_delivery_rate_policies(django_apps, None)
    return {policy.channel: policy for policy in DeliveryRatePolicy.objects.all()}


def active_email(provider="ses", max_send_rate=10):
    return EmailServiceConfig.objects.create(
        name="Mail", is_active=True, provider=provider, from_email="i2g@example.edu", max_send_rate=max_send_rate
    )


def rates_with(channel, **values):
    rates = copy.deepcopy(settings.DELIVERY_RATES)
    rates["channels"][channel].update(values)
    return rates


class RateControlMigrationGraphTests(SimpleTestCase):
    def test_0036_follows_0035_and_0037_follows_it(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)

        self.assertEqual(len([node for node in loader.graph.leaf_nodes() if node[0] == "core"]), 1)
        self.assertEqual({parent.key for parent in loader.graph.node_map[RATE_CONTROL].parents}, {GRAPH_CERTIFICATES})
        self.assertEqual({parent.key for parent in loader.graph.node_map[RETIRED_RATES].parents}, {RATE_CONTROL})

    def test_the_frozen_channels_and_seed_fields_match_the_models(self):
        self.assertEqual([value for value, _label in migration.CHANNEL_CHOICES], Channel.values)
        policy_fields = {field.name for field in DeliveryRatePolicy._meta.get_fields()}
        self.assertLessEqual(set(migration.SEED_FIELDS), policy_fields)


class RateControlSeedTests(TestCase):
    def setUp(self):
        cache.clear()
        DeliveryRatePolicy.objects.all().delete()

    def test_without_an_email_config_every_channel_gets_its_settings_seed_with_smart_rate_on(self):
        policies = seed()

        self.assertEqual(set(policies), set(Channel.values))
        for channel, policy in policies.items():
            with self.subTest(channel=channel):
                self.assertTrue(policy.smart_enabled)
                self.assertEqual(policy.manual_rate, DeliveryRatePolicy.seed_values(channel)["manual_rate"])
                policy.full_clean()
        self.assertEqual((policies["ses_send"].manual_rate, policies["ses_send"].provider_limit), (Decimal(10), None))
        self.assertEqual(policies["smtp_send"].manual_rate, Decimal(30))
        self.assertEqual(policies["graph_send"].manual_rate, Decimal(24))
        self.assertEqual(policies["gmail_api_send"].transactional_reserve, Decimal("0.250"))

    def test_the_ses_campaign_rate_becomes_its_manual_rate_and_provider_limit(self):
        active_email(max_send_rate=7)
        policies = seed()

        self.assertEqual(
            (policies["ses_send"].manual_rate, policies["ses_send"].provider_limit), (Decimal(7), Decimal(7))
        )
        self.assertTrue(policies["ses_send"].smart_enabled)
        self.assertEqual(policies["smtp_send"].manual_rate, Decimal(30))
        policies["ses_send"].full_clean()

    def test_a_zero_campaign_rate_keeps_the_defaults(self):
        active_email(max_send_rate=0)
        policies = seed()

        self.assertEqual((policies["ses_send"].manual_rate, policies["ses_send"].provider_limit), (Decimal(10), None))

    def test_smtp_takes_the_campaign_rate_per_minute_only_while_smtp_sends(self):
        active_email(provider="smtp", max_send_rate=7)
        policies = seed()

        self.assertEqual(policies["smtp_send"].manual_rate, Decimal(420))
        self.assertEqual(policies["ses_send"].manual_rate, Decimal(7))
        policies["smtp_send"].full_clean()

    def test_an_inactive_email_config_is_ignored(self):
        EmailServiceConfig.objects.create(name="Old", is_active=False, provider="smtp", max_send_rate=3)
        policies = seed()

        self.assertEqual(policies["ses_send"].manual_rate, Decimal(10))
        self.assertEqual(policies["smtp_send"].manual_rate, Decimal(30))

    def test_carried_over_rates_are_capped_at_the_documented_limits(self):
        active_email(provider="smtp", max_send_rate=7)
        rates = rates_with(Channel.SES_SEND, provider_limit=5)
        rates["channels"]["smtp_send"]["provider_limit"] = 100
        with override_settings(DELIVERY_RATES=rates):
            policies = seed()
            for policy in policies.values():
                policy.full_clean()

        self.assertEqual(
            (policies["ses_send"].manual_rate, policies["ses_send"].provider_limit), (Decimal(5), Decimal(5))
        )
        self.assertEqual(policies["smtp_send"].manual_rate, Decimal(100))

    def test_a_rate_too_large_for_the_column_keeps_the_default(self):
        active_email(provider="smtp", max_send_rate=200_000)
        policies = seed()

        self.assertEqual(policies["ses_send"].manual_rate, Decimal(200_000))
        self.assertEqual(policies["smtp_send"].manual_rate, Decimal(30))  # 12,000,000/min does not fit Decimal(10, 3)

    def test_existing_rows_are_kept(self):
        DeliveryRatePolicy.objects.create(channel=Channel.SES_SEND, manual_rate=Decimal(3), smart_enabled=False)
        active_email(max_send_rate=7)
        policies = seed()

        self.assertEqual((policies["ses_send"].manual_rate, policies["ses_send"].smart_enabled), (Decimal(3), False))

    def test_a_channel_missing_from_the_settings_is_left_for_first_use(self):
        rates = copy.deepcopy(settings.DELIVERY_RATES)
        del rates["channels"]["sms_send"]
        with override_settings(DELIVERY_RATES=rates):
            policies = seed()
        self.assertNotIn("sms_send", policies)
        self.assertEqual(len(policies), len(Channel.values) - 1)

    def test_the_reverse_removes_the_rows(self):
        seed()
        migration.remove_delivery_rate_policies(django_apps, None)
        self.assertFalse(DeliveryRatePolicy.objects.exists())


class RateControlMigrationRoundTripTests(TransactionTestCase):
    """Migrate core back to 0035 and forward again, with a pre-existing campaign send rate."""

    def tearDown(self):
        # Leave the schema fully migrated for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def tables(self):
        with connection.cursor() as cursor:
            return set(connection.introspection.table_names(cursor))

    def job_columns(self):
        with connection.cursor() as cursor:
            return {
                column.name for column in connection.introspection.get_table_description(cursor, "core_backgroundjob")
            }

    def test_forward_seeds_from_the_active_config_and_reverse_drops_everything(self):
        executor = MigrationExecutor(connection)
        executor.migrate([GRAPH_CERTIFICATES])
        self.assertFalse(set(RATE_TABLES) & self.tables())
        self.assertNotIn("priority", self.job_columns())
        old_apps = executor.loader.project_state([GRAPH_CERTIFICATES]).apps
        old_apps.get_model("core", "EmailServiceConfig").objects.create(
            name="Mail", is_active=True, provider="ses", from_email="a@b.co", max_send_rate=7
        )
        old_apps.get_model("core", "MicrosoftGraphProviderConfig").objects.create(
            name="Mail", is_active=True, tenant_id="contoso.com", client_id="app", messages_per_minute=20
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([RATE_CONTROL])

        self.assertTrue(set(RATE_TABLES) <= self.tables())
        self.assertIn("priority", self.job_columns())
        new_apps = executor.loader.project_state([RATE_CONTROL]).apps
        policies = {row.channel: row for row in new_apps.get_model("core", "DeliveryRatePolicy").objects.all()}
        self.assertEqual(set(policies), set(Channel.values))
        self.assertTrue(all(policy.smart_enabled for policy in policies.values()))
        self.assertEqual(
            (policies["ses_send"].manual_rate, policies["ses_send"].provider_limit), (Decimal(7), Decimal(7))
        )
        # The active Graph config's rate becomes the Graph manual rate.
        self.assertEqual(policies["graph_send"].manual_rate, Decimal(20))

        executor = MigrationExecutor(connection)
        executor.migrate([GRAPH_CERTIFICATES])
        self.assertFalse(set(RATE_TABLES) & self.tables())
        self.assertNotIn("priority", self.job_columns())


class RetireOldSendRatesMigrationTests(TransactionTestCase):
    """Migration 0037 drops the Graph messages-per-minute column (its value lives on as the Graph manual rate) and
    keeps EmailServiceConfig.max_send_rate, no longer editable, for one release."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def graph_columns(self):
        with connection.cursor() as cursor:
            table = "core_microsoftgraphproviderconfig"
            return {column.name for column in connection.introspection.get_table_description(cursor, table)}

    def test_forward_drops_the_graph_rate_column_and_reverse_restores_its_default(self):
        executor = MigrationExecutor(connection)
        executor.migrate([RATE_CONTROL])
        self.assertIn("messages_per_minute", self.graph_columns())

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([RETIRED_RATES])
        self.assertNotIn("messages_per_minute", self.graph_columns())
        self.assertFalse(EmailServiceConfig._meta.get_field("max_send_rate").editable)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([RATE_CONTROL])
        self.assertIn("messages_per_minute", self.graph_columns())
