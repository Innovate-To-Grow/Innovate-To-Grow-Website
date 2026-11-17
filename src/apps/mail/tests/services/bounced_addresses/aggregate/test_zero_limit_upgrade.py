"""The 0 KB rule upgrade corrects stored reports while keeping staff decisions."""

import importlib
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from apps.mail.models import BounceAggregationState, BouncedAddress
from apps.mail.services.email_monitoring.addresses import aggregate

from ..helpers import count_now, make_bounce

migration = importlib.import_module("apps.mail.migrations.0029_alter_bouncedaddress_suggestion")


class ZeroLimitUpgradeTests(TestCase):
    def test_old_zero_limit_is_retried_without_losing_review_or_suppression(self):
        bounce = make_bounce(
            recipient="limited@example.org",
            category="mailbox_disabled",
            classification="hard",
            status_code="5.2.3",
            diagnostic_code="550 5.2.3 Mailbox disabled; Max size allowed: 0 KB",
            is_permanent=True,
        )
        count_now()
        row = BouncedAddress.objects.get(address="limited@example.org")
        row.status = BouncedAddress.Status.DISMISSED
        row.suppression = BouncedAddress.Suppression.UNDELIVERABLE
        row.suppressed_at = bounce.received_at
        row.save(update_fields=["status", "suppression", "suppressed_at"])

        migration.reclassify_zero_limits(apps, SimpleNamespace(connection=connection))

        bounce.refresh_from_db()
        self.assertEqual((bounce.category, bounce.classification, bounce.is_permanent), ("transient", "soft", False))
        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, aggregate.PARKED)
        count_now()
        row.refresh_from_db()
        self.assertEqual((row.hard_count, row.soft_count, row.category_counts), (0, 1, {"transient": 1}))
        self.assertEqual(
            (row.status, row.suppression, row.suppressed_at), ("dismissed", "undeliverable", bounce.received_at)
        )

    def test_unrelated_disabled_mailbox_is_not_reclassified(self):
        bounce = make_bounce(
            recipient="closed@example.org",
            category="mailbox_disabled",
            classification="hard",
            status_code="5.2.1",
            diagnostic_code="550 5.2.1 This mailbox is disabled",
        )
        migration.reclassify_zero_limits(apps, SimpleNamespace(connection=connection))
        bounce.refresh_from_db()
        self.assertEqual((bounce.category, bounce.classification), ("mailbox_disabled", "hard"))
        self.assertFalse(BounceAggregationState.objects.filter(source="graph").exists())
