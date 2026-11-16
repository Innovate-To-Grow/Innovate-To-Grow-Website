from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.project.models.delivery_rates.test_delivery_rate_migration import (
    GRAPH_CERTIFICATES,
    RATE_CONTROL,
    RATE_TABLES,
    RETIRED_RATES,
    Channel,
)


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
    """Migration 0037 hides the Graph messages-per-minute and the campaign send rate fields (their values live on in
    the delivery-rate policies) but keeps both columns for one release: production migrates before it replaces the
    service, and an image rollback never reverses DDL, so a task of the previous release must still read them."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def graph_columns(self):
        with connection.cursor() as cursor:
            table = "core_microsoftgraphproviderconfig"
            return {column.name for column in connection.introspection.get_table_description(cursor, table)}

    def test_forward_hides_both_fields_but_keeps_their_columns_and_reverses(self):
        executor = MigrationExecutor(connection)
        executor.migrate([RATE_CONTROL])
        self.assertIn("messages_per_minute", self.graph_columns())

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([RETIRED_RATES])
        self.assertIn("messages_per_minute", self.graph_columns())
        retired = executor.loader.project_state([RETIRED_RATES]).apps
        for model, name in (
            ("MicrosoftGraphProviderConfig", "messages_per_minute"),
            ("EmailServiceConfig", "max_send_rate"),
        ):
            with self.subTest(field=name):
                self.assertFalse(retired.get_model("core", model)._meta.get_field(name).editable)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([RATE_CONTROL])
        self.assertIn("messages_per_minute", self.graph_columns())

    def test_a_row_created_now_holds_a_rate_the_previous_release_accepts(self):
        config = create_graph_config(name="Mail", certificate=False)

        stored = MicrosoftGraphProviderConfig.objects.values_list("messages_per_minute", flat=True).get(pk=config.pk)
        # The previous release validates 1-30 and defaulted to 24.
        self.assertEqual(stored, 24)
        self.assertFalse(MicrosoftGraphProviderConfig._meta.get_field("messages_per_minute").editable)
