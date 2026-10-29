"""Migration 0034: Graph configs saved before certificates keep working (client secret + send-only scope)."""

import importlib

from django.apps import apps as global_apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig

MIGRATION = importlib.import_module("apps.core.migrations.0034_graph_certificate_and_mailbox_scope")
BEFORE = [("core", "0033_microsoft_graph_provider")]
AFTER = [("core", "0034_graph_certificate_and_mailbox_scope")]
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class KeepExistingConfigsWorkingTests(TestCase):
    """The data function against the current models (rows that already exist when 0034 runs)."""

    def insert(self, **values):
        row = MicrosoftGraphProviderConfig(name="Old", tenant_id=TENANT_ID, client_id=CLIENT_ID, **values)
        MicrosoftGraphProviderConfig.objects.bulk_create([row])
        return row

    def test_existing_rows_switch_to_client_secret_with_a_send_only_scope(self):
        row = self.insert(client_secret="not-a-real-secret", mailbox="Sender@Contoso.com")

        MIGRATION.keep_existing_configs_working(global_apps, None)

        row.refresh_from_db()
        self.assertEqual(row.auth_method, MicrosoftGraphProviderConfig.AuthMethod.CLIENT_SECRET)
        scope = row.mailbox_scopes.get()
        self.assertEqual((scope.mailbox, scope.permission), ("sender@contoso.com", "send"))

    def test_rows_without_a_mailbox_get_no_scope(self):
        row = self.insert(client_secret="not-a-real-secret", mailbox="")

        MIGRATION.keep_existing_configs_working(global_apps, None)

        row.refresh_from_db()
        self.assertEqual(row.auth_method, "client_secret")
        self.assertFalse(row.mailbox_scopes.exists())

    def test_an_existing_scope_row_is_kept(self):
        row = self.insert(client_secret="not-a-real-secret", mailbox="sender@contoso.com")
        MicrosoftGraphMailboxScope.objects.create(config=row, mailbox="sender@contoso.com", permission="send_read")

        MIGRATION.keep_existing_configs_working(global_apps, None)
        MIGRATION.keep_existing_configs_working(global_apps, None)

        self.assertEqual(list(row.mailbox_scopes.values_list("permission", flat=True)), ["send_read"])


class Migration0034ForwardTests(TransactionTestCase):
    """Migrate core back to 0033, insert a row with the historical model, and migrate forward."""

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Config = old_apps.get_model("core", "MicrosoftGraphProviderConfig")
        self.with_mailbox = Config.objects.create(
            name="Old", is_active=True, tenant_id=TENANT_ID, client_id=CLIENT_ID,
            client_secret="not-a-real-secret", mailbox="Sender@Contoso.com",
        )  # fmt: skip
        self.without_mailbox = Config.objects.create(
            name="Older", tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret="not-a-real-secret"
        )
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)

    def tearDown(self):
        # Leave the schema fully migrated for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_rows_saved_before_0034_keep_sending(self):
        migrated = MicrosoftGraphProviderConfig.objects.get(pk=self.with_mailbox.pk)

        self.assertEqual(migrated.auth_method, "client_secret")
        self.assertEqual(migrated.client_secret, "not-a-real-secret")
        self.assertEqual((migrated.certificate, migrated.private_key, migrated.certificate_thumbprint), ("", "", ""))
        self.assertEqual(
            list(migrated.mailbox_scopes.values_list("mailbox", "permission")), [("sender@contoso.com", "send")]
        )
        self.assertTrue(migrated.is_configured)
        self.assertTrue(migrated.sending_ready("sender@contoso.com"))
        self.assertFalse(migrated.allows("sender@contoso.com", "read"))

        other = MicrosoftGraphProviderConfig.objects.get(pk=self.without_mailbox.pk)
        self.assertEqual(other.auth_method, "client_secret")
        self.assertFalse(other.mailbox_scopes.exists())
