"""Exact per-campaign Graph evidence stays separate from likely aggregate matches."""

import importlib
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.services.email_monitoring.helpers import make_bounce
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, EmailCampaign
from apps.mail.services.email_monitoring.addresses.aggregate.graph_source import _link_graph
from apps.mail.tests.services.campaigns.retry.helpers import make_retry_campaign

migration = importlib.import_module("apps.mail.migrations.0031_email_retry_safety")


class RetryEvidenceTests(TestCase):
    def test_likely_category_does_not_mix_into_later_exact_link(self):
        campaign = EmailCampaign.objects.create(subject="Source", body="Body")
        row = BouncedAddress.objects.create(address="mixed@example.org")
        now = timezone.now()

        _link_graph(row, campaign.pk, BouncedAddressCampaign.Match.LIKELY, now, "transient")
        _link_graph(row, campaign.pk, BouncedAddressCampaign.Match.EXACT, now, "policy_rejected")

        link = BouncedAddressCampaign.objects.get(bounced_address=row, campaign_id=campaign.pk, source="graph")
        self.assertEqual(link.match, "exact")
        self.assertEqual(link.graph_category_counts, {"policy_rejected": 1})

    def test_migration_backfills_only_retained_exact_campaign_evidence(self):
        exact_campaign = EmailCampaign.objects.create(subject="Exact", body="Body")
        likely_campaign = EmailCampaign.objects.create(subject="Likely", body="Body")
        exact_row = BouncedAddress.objects.create(address="exact@example.org")
        likely_row = BouncedAddress.objects.create(address="likely@example.org")
        for row, campaign in ((exact_row, exact_campaign), (likely_row, likely_campaign)):
            BouncedAddressCampaign.objects.create(
                bounced_address=row,
                campaign_id=campaign.pk,
                source="graph",
                match="likely",
                bounce_count=1,
            )
        make_bounce(
            recipient="exact@example.org",
            category="transient",
            classification="soft",
            campaign_id=exact_campaign.pk,
            match_method="message_id",
        )
        make_bounce(
            recipient="likely@example.org",
            category="transient",
            classification="soft",
            campaign_id=None,
            match_method="unmatched",
        )

        migration.backfill_exact_graph_categories(apps, SimpleNamespace(connection=connection))

        exact = BouncedAddressCampaign.objects.get(bounced_address=exact_row)
        likely = BouncedAddressCampaign.objects.get(bounced_address=likely_row)
        self.assertEqual((exact.match, exact.graph_category_counts), ("exact", {"transient": 1}))
        self.assertEqual((likely.match, likely.graph_category_counts), ("likely", {}))

    def test_migration_reverse_refuses_to_drop_live_retry_provenance(self):
        schema_editor = SimpleNamespace(connection=connection)
        migration.prevent_unsafe_reverse(apps, schema_editor)
        make_retry_campaign()

        with self.assertRaisesMessage(RuntimeError, "Cannot reverse mail.0031 while retry campaigns exist"):
            migration.prevent_unsafe_reverse(apps, schema_editor)
