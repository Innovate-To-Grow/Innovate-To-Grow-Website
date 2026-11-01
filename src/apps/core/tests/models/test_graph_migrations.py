"""Migrations 0034/0035: they follow main's 0033, create no secret or token column, and reverse cleanly."""

import importlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TransactionTestCase

from apps.core.admin.mixins.confirm_on_save_utils import SENSITIVE_FIELD_RE as CONFIRM_SENSITIVE_FIELD_RE
from apps.core.services.db_tools.safe_orm import SENSITIVE_FIELD_RE as SAFE_ORM_SENSITIVE_FIELD_RE

MAIN_0033 = ("core", "0033_awscredentialconfig_credentials_secret_arn")
PROVIDER = ("core", "0034_microsoft_graph_provider")
CERTIFICATES = ("core", "0035_graph_certificate_and_mailbox_scope")
GRAPH_TABLES = (
    "core_microsoftgraphproviderconfig",
    "core_microsoftgraphmailboxscope",
    "core_microsoftgraphcertificate",
    "core_microsoftgraphaccesscheck",
)


class GraphMigrationGraphTests(SimpleTestCase):
    def test_the_graph_migrations_follow_main_and_leave_one_core_leaf(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)

        self.assertEqual([node for node in loader.graph.leaf_nodes() if node[0] == "core"], [CERTIFICATES])
        self.assertEqual({parent.key for parent in loader.graph.node_map[PROVIDER].parents}, {MAIN_0033})
        # 0035 also depends on the user model (the access check's ``run_by``), as earlier core migrations do.
        certificate_parents = {parent.key for parent in loader.graph.node_map[CERTIFICATES].parents}
        self.assertEqual({key for key in certificate_parents if key[0] == "core"}, {PROVIDER})

    def test_no_operation_creates_a_secret_column(self):
        for name in (PROVIDER[1], CERTIFICATES[1]):
            module = importlib.import_module(f"apps.core.migrations.{name}")
            for operation in module.Migration.operations:
                for field_name, _field in getattr(operation, "fields", ()):
                    with self.subTest(migration=name, field=field_name):
                        self.assertIsNone(CONFIRM_SENSITIVE_FIELD_RE.search(field_name))
                        self.assertIsNone(SAFE_ORM_SENSITIVE_FIELD_RE.search(field_name))


class GraphMigrationRoundTripTests(TransactionTestCase):
    """Migrate core back to main's 0033 and forward again."""

    def tearDown(self):
        # Leave the schema fully migrated for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def tables(self):
        with connection.cursor() as cursor:
            return set(connection.introspection.table_names(cursor))

    def test_reversing_drops_the_graph_tables_and_moves_graph_senders_back_to_ses(self):
        executor = MigrationExecutor(connection)
        executor.migrate([CERTIFICATES])
        EmailServiceConfig = executor.loader.project_state([CERTIFICATES]).apps.get_model("core", "EmailServiceConfig")
        sender = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email="a@b.co")

        executor = MigrationExecutor(connection)
        executor.migrate([MAIN_0033])

        self.assertFalse(set(GRAPH_TABLES) & self.tables())
        sender.refresh_from_db()
        self.assertEqual(sender.provider, "ses")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([CERTIFICATES])
        self.assertTrue(set(GRAPH_TABLES) <= self.tables())
