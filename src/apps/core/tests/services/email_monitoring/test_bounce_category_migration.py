"""Migration core.0047: bounce categories. Its frozen classifier, the backfill of stored reports (and each email's
worst classification), and the round trip from core.0046, including a report saved by the release before categories
while the deploy rolls out (the database defaults)."""

import importlib

from django.apps import apps as django_apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.services.email.bounces.dsn import parse_report

from .helpers import make_bounce, make_email
from .review_cases import CASES

migration = importlib.import_module("apps.core.migrations.0047_email_bounce_category")
BEFORE = ("core", "0046_inbound_message")
AFTER = ("core", "0047_email_bounce_category")
EXPIRED = "550 5.4.316 Message expired, connection refused(Socket error code 10061)"


class FrozenClassifierTests(SimpleTestCase):
    def test_the_frozen_copy_gives_each_review_case_its_category(self):
        for case in CASES:
            with self.subTest(case=case.name):
                (row,) = parse_report(case.raw).recipients
                classification, category, permanent, _reason, smtp = migration.classify(
                    row.action, row.status, row.diagnostic
                )
                expected = case.expected
                self.assertEqual(
                    (category, classification, permanent, smtp),
                    (expected.category, expected.classification, expected.is_permanent, expected.smtp_code),
                )

    def test_the_frozen_copy_follows_the_rules_of_its_time(self):
        self.assertEqual(migration.classify("failed", "5.0.0", "")[:3], ("unknown", "unknown", None))
        self.assertEqual(migration.classify("failed", "4.7.1", "454 4.7.1 Relay access denied")[1], "relay_denied")
        self.assertEqual(migration.classify("failed", "5.4.4", "Host not found, try again")[1], "transient")
        self.assertEqual(migration.classify("failed", "5.0.0", "said: 550 5.1.1 x")[1], "hard")
        self.assertEqual(migration.classify("failed", "5.2.3", "Max size allowed: 0 KB")[1], "mailbox_disabled")
        self.assertEqual(migration.classify("failed", "5.0.0", "message size limit of 0 KB")[1], "mailbox_disabled")
        self.assertEqual(migration.classify("failed", "5.7.613", "")[1], "spam_rejected")
        self.assertEqual(migration.classify("failed", "5.1.99", "")[3], "Recipient address problem")
        self.assertEqual(migration.classify("failed", "", ""), migration.NO_VERDICT)
        self.assertEqual(migration.classify("delayed", "4.4.7", "")[:2], ("delayed", "delayed"))
        self.assertIsNone(migration.classify("delivered", "2.0.0", ""))


class BackfillTests(TestCase):
    def test_stored_reports_get_categories_and_emails_their_worst_classification_again(self):
        email = make_email(delivery_status="failure_confirmed", bounce_classification="hard")
        expired = make_bounce(
            email=email, category="", is_permanent=True, status_code="5.4.316", diagnostic_code=EXPIRED
        )
        spam = make_bounce(
            email=email,
            category="",
            classification="rejected",
            status_code="5.7.1",
            diagnostic_code="550 5.7.1 Message rejected as spam",
        )
        delay = make_bounce(email=email, category="", action="delayed", classification="delayed", status_code="4.4.7")
        missing = make_bounce(category="", status_code="5.1.1", diagnostic_code="550 5.1.1 user unknown")
        odd = make_bounce(category="", action="delivered", status_code="2.0.0")

        migration.classify_stored_reports(django_apps, None)

        for row in (expired, spam, delay, missing, odd):
            row.refresh_from_db()
        self.assertEqual(
            (expired.category, expired.classification, expired.is_permanent, expired.smtp_code, expired.reason),
            ("transient", "soft", False, "550", "Delivery expired: connection refused"),
        )
        self.assertEqual((spam.category, spam.classification), ("spam_rejected", "rejected"))
        self.assertEqual((delay.category, delay.classification), ("delayed", "delayed"))
        self.assertEqual((missing.category, missing.is_permanent), ("hard", True))
        self.assertEqual((odd.category, odd.classification), ("unknown", "unknown"))
        email.refresh_from_db()
        self.assertEqual(email.bounce_classification, "rejected")

    def test_an_empty_table_is_left_alone(self):
        migration.classify_stored_reports(django_apps, None)


class RoundTripTests(TransactionTestCase):
    """Migrate core back to 0046 and forward again (mail.0026 depends on 0047, so it moves with it)."""

    def tearDown(self):
        # Leave the schema fully migrated for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def columns(self):
        with connection.cursor() as cursor:
            return {
                column.name for column in connection.introspection.get_table_description(cursor, "core_emailbounce")
            }

    def test_forward_classifies_stored_reports_old_saves_get_the_defaults_and_reverse_drops_the_columns(self):
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        self.assertFalse({"category", "smtp_code"} & self.columns())
        old_bounce = executor.loader.project_state([BEFORE]).apps.get_model("core", "EmailBounce")
        values = {"mailbox": "i2g@ucmerced.edu", "ndr_graph_id": "g", "received_at": timezone.now(), "action": "failed"}
        old_bounce.objects.create(
            dedupe_key="before",
            recipient="refused@example.org",
            status_code="5.4.316",
            diagnostic_code=EXPIRED,
            classification="hard",
            is_permanent=True,
            **values,
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([AFTER])

        new_bounce = executor.loader.project_state([AFTER]).apps.get_model("core", "EmailBounce")
        row = new_bounce.objects.get(dedupe_key="before")
        self.assertEqual(
            (row.category, row.classification, row.is_permanent, row.smtp_code), ("transient", "soft", False, "550")
        )
        # The previous release, still running while the deploy rolls out, saves without the new columns.
        old_bounce.objects.create(dedupe_key="during", recipient="x@example.org", classification="hard", **values)
        self.assertEqual(
            new_bounce.objects.filter(dedupe_key="during").values_list("category", "smtp_code").get(), ("", "")
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([BEFORE])
        self.assertFalse({"category", "smtp_code"} & self.columns())
        self.assertEqual(old_bounce.objects.get(dedupe_key="before").classification, "soft")
