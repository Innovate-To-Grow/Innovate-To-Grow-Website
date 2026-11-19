"""Historical review-only evidence, including rows whose raw DSNs expired."""

from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from apps.core.services.email.bounces.classify import classify
from apps.mail.migrations._graph_review_v1 import preserve_graph_history
from apps.mail.models import BouncedAddress
from apps.mail.services.campaign.content.retry import retry_eligibility_for
from apps.mail.tests.services.bounced_addresses.helpers import count_now, make_bounce
from apps.mail.tests.services.campaigns.retry.helpers import make_retry_campaign

migration = import_module("apps.mail.migrations.0032_recipient_bound_bounce_review")


class GraphEvidenceUpgradeTests(TestCase):
    def test_purged_hard_report_blocks_retry_after_unrelated_zero_limit_migrates(self):
        address = "legacy@example.org"
        _, campaign, _, row, _ = make_retry_campaign(address=address)
        # The summary is the only remaining permanent evidence; its raw DSN has expired.
        row.hard_count = 1
        row.category_counts = {"hard": 1, "transient": 1}
        row.save()
        make_bounce(
            recipient=address,
            category="transient",
            classification="soft",
            status_code="4.4.1",
            match_method="message_id",
            trusted_recipient=True,
            campaign_id=campaign.pk,
        )
        make_bounce(
            recipient="other@example.org",
            category="mailbox_disabled",
            classification="hard",
            status_code="5.2.3",
            diagnostic_code="550 5.2.3 Mailbox disabled; Max size allowed: 0 KB",
        )
        schema = SimpleNamespace(connection=connection)
        migration.reconcile_existing_reports(apps, schema)
        preserve_graph_history(apps, schema)
        count_now()
        row.refresh_from_db()
        self.assertTrue(row.legacy_graph_permanent_review)
        self.assertEqual(row.category_counts["hard"], 1)
        self.assertIsNone(row.suppressed_at)
        self.assertIsNone(row.trusted_graph_last_permanent_at)
        self.assertIsNone(retry_eligibility_for(campaign, address))
        # All the other prerequisites are met; only an explicit review could release this hold.
        BouncedAddress.objects.filter(pk=row.pk).update(legacy_graph_permanent_review=False)
        self.assertIsNotNone(retry_eligibility_for(campaign, address))
        self.assertEqual(BouncedAddress.objects.get(address="other@example.org").category_counts, {"transient": 1})

    def test_late_old_rule_sender_rejections_and_conflicts_are_reclassified(self):
        for diagnostic, expected in (
            ("550 5.4.1 Relay access denied", "relay_denied"),
            ("550 5.4.1 Rejected as spam", "spam_rejected"),
            ("550 5.4.1 User unknown; relay access denied", "unknown"),
        ):
            event = make_bounce(
                recipient="valid@example.org",
                category="hard",
                classification="hard",
                status_code="5.4.1",
                diagnostic_code=diagnostic,
            )
            migration.reconcile_existing_reports(apps, SimpleNamespace(connection=connection))
            event.refresh_from_db()
            self.assertEqual(event.category, expected)
            self.assertFalse(event.is_permanent)
        count_now()
        row = BouncedAddress.objects.get(address="valid@example.org")
        self.assertEqual(row.category_counts, {"relay_denied": 1, "spam_rejected": 1, "unknown": 1})
        self.assertFalse(row.legacy_graph_permanent_review)

    def test_persisted_routing_diagnostics_match_the_runtime_verdict(self):
        for status, text in (
            ("5.4.1", "Recipient address rejected: Access denied"),
            ("5.4.4", "Unable to route"),
            ("5.4.1", "No answer from host"),
            ("5.4.4", "Recipient domain does not exist"),
            ("5.4.4", "Max size allowed: 0 KB; user unknown"),
        ):
            diagnostic = f"550 {status} {text}"
            event = make_bounce(
                recipient="route@example.org",
                status_code=status,
                diagnostic_code=diagnostic,
                classification="hard",
                category="hard",
            )
            migration.reconcile_existing_reports(apps, SimpleNamespace(connection=connection))
            expected = classify("failed", status, diagnostic)
            event.refresh_from_db()
            self.assertEqual(
                (event.classification, event.category, event.is_permanent, event.reason),
                (expected.classification, expected.category, expected.is_permanent, expected.reason),
                diagnostic,
            )
