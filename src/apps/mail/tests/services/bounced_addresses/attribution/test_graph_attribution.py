"""Only a DSN for the final envelope recipient of the identified message authorizes campaign actions."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.recording.dsn import parse_report
from apps.core.services.email.bounces.recording.store import save_report
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.core.tests.services.email_monitoring.ndr_samples import ORIGINAL_ID, exchange_ndr
from apps.mail.models import BouncedAddress
from apps.mail.services.campaign.content.retry_evidence import graph_campaign_categories
from apps.mail.services.email_monitoring.addresses.policies.graph import graph_hold_addresses, row_has_graph_hold

from ..helpers import count_now, make_campaign


class GraphAttributionTests(TestCase):
    address = "nobody@example.com"

    def setUp(self):
        self.campaign = make_campaign("Graph source")
        self.row = BouncedAddress.objects.create(address=self.address)

    def save(self, raw, received_at=None):
        result = save_report(
            mailbox="staff@example.org",
            graph_id="synthetic",
            received_at=received_at or timezone.now(),
            report=parse_report(raw),
        )
        return result.created[0]

    def categories(self):
        return graph_campaign_categories(self.row, self.campaign, self.address)

    def test_inferred_temporary_is_review_only_and_does_not_become_exact_when_other_evidence_arrives(self):
        make_email(recipient=self.address, campaign_id=self.campaign.pk, subject="Announcement")
        inferred = self.save(exchange_ndr(subject="Announcement", status="5.2.2"))
        self.assertEqual(inferred.match_method, "recipient")
        self.assertFalse(inferred.trusted_recipient)
        count_now()
        self.assertEqual(self.categories(), set())
        self.assertEqual(self.row.campaign_links.get().match, "likely")

        make_email(recipient=self.address, campaign_id=self.campaign.pk, internet_message_id=ORIGINAL_ID)
        self.save(exchange_ndr(status="5.7.12", report_id="<policy@example.org>"))
        self.assertEqual(self.categories(), {"policy_rejected"})
        count_now()
        self.assertEqual(self.categories(), {"policy_rejected"})
        self.assertEqual(self.row.campaign_links.get().match, "exact")

    def test_old_message_id_wrong_recipient_and_forwarded_reports_cannot_hold_or_authorize_retry(self):
        make_email(
            campaign_id=self.campaign.pk, recipient="other@example.org", internet_message_id="<other@example.org>"
        )
        wrong = self.save(exchange_ndr(original_id="<other@example.org>"))
        make_email(campaign_id=self.campaign.pk, recipient=self.address, internet_message_id=ORIGINAL_ID)
        forwarded = exchange_ndr(status="5.2.2", report_id="<forwarded@example.org>").replace(
            b"Final-Recipient: rfc822;nobody@example.com", b"Final-Recipient: rfc822;former@example.org"
        )
        self.assertFalse(self.save(forwarded).trusted_recipient)
        self.assertFalse(wrong.trusted_recipient)
        self.assertFalse(graph_hold_addresses([self.address]))
        count_now()
        self.assertFalse(graph_hold_addresses([self.address]))
        self.assertEqual(self.categories(), set())

    def test_verified_hold_is_immediate_survives_retention_and_only_a_newer_failure_reactivates_it(self):
        make_email(campaign_id=self.campaign.pk, recipient=self.address, internet_message_id=ORIGINAL_ID)
        past = timezone.now() - timedelta(minutes=3)
        bounce = self.save(exchange_ndr(), past)
        self.assertTrue(bounce.trusted_recipient)
        self.assertEqual(set(graph_hold_addresses([self.address])), {self.address})
        count_now()
        self.row.refresh_from_db()
        self.assertEqual((self.row.trusted_graph_hard_count, self.row.trusted_graph_disabled_count), (1, 0))
        self.assertTrue(row_has_graph_hold(self.row))
        cleared = past + timedelta(minutes=1)
        BouncedAddress.objects.filter(pk=self.row.pk).update(graph_hold_cleared_at=cleared)
        self.assertFalse(graph_hold_addresses([self.address]))
        self.save(exchange_ndr(report_id="<before@example.org>"), past)
        self.assertFalse(graph_hold_addresses([self.address]))
        self.save(exchange_ndr(status="5.2.1", report_id="<after@example.org>"), cleared + timedelta(minutes=1))
        self.assertEqual(set(graph_hold_addresses([self.address])), {self.address})
        count_now()
        EmailBounce.objects.all().delete()
        self.row.refresh_from_db()
        self.assertEqual(self.row.trusted_graph_disabled_count, 1)
        self.assertTrue(row_has_graph_hold(self.row))
        self.assertEqual(set(graph_hold_addresses([self.address])), {self.address})
