from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.tests.services.email_monitoring.helpers import make_bounce
from apps.event.tests.helpers import make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressAction, RecipientLog
from apps.mail.services.audience import get_recipients
from apps.mail.services.audience.suppression import SKIPPED_MESSAGE, is_suppressed
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.campaign.send.runner import send_campaign
from apps.mail.tests.services.bounced_addresses.actions.test_actions import apply

from .test_send_path import _make_active_aws, campaign, suppress


class ConfirmedHoldTests(TestCase):
    address = "target@example.org"

    def confirmed(self, **overrides):
        values = {
            "recipient": self.address,
            "category": "hard",
            "classification": "hard",
            "status_code": "5.1.1",
            "trusted_recipient": True,
            "match_method": "message_id",
        }
        return make_bounce(**{**values, **overrides})

    def test_normal_bulk_audience_skips_confirmed_recipient_only(self):
        for category in ("transient", "relay_denied", "spam_rejected"):
            self.confirmed(category=category, recipient=f"{category}@example.org")
        self.confirmed(trusted_recipient=False, recipient="unmatched@example.org")
        self.confirmed()
        others = [
            "transient@example.org",
            "relay_denied@example.org",
            "spam_rejected@example.org",
            "unmatched@example.org",
        ]
        blast = campaign(audience_type="manual", manual_emails="\n".join([self.address, *others]))
        self.assertEqual({r["email"] for r in get_recipients(blast)}, set(others))

    def test_clear_only_releases_reviewed_evidence(self):
        first = self.confirmed()
        row = BouncedAddress.objects.create(
            address=self.address,
            trusted_graph_last_permanent_at=first.received_at,
            trusted_graph_hard_count=1,
            legacy_graph_permanent_review=True,
        )
        self.assertTrue(is_suppressed(self.address))
        apply(make_superuser(), row, BouncedAddressAction.Action.CLEAR_SUPPRESSION, note="Current owner verified")
        row.refresh_from_db()
        self.assertFalse(row.legacy_graph_permanent_review)
        self.assertFalse(is_suppressed(self.address))
        self.confirmed(received_at=first.received_at + timezone.timedelta(minutes=1))
        self.assertTrue(is_suppressed(self.address))

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
    def test_new_graph_failure_while_worker_waits(self, transport, _client):
        def enter(*, before_provider_call, **_kwargs):
            self.confirmed()
            before_provider_call()
            self.fail("Transport crossed the provider boundary")

        transport.side_effect = enter
        EmailServiceConfig.objects.create(is_active=True, from_email="sender@example.org")
        blast = campaign(audience_type="manual", manual_emails=self.address)
        queue_email_campaign(blast, sent_by=make_superuser())
        self.assertTrue(process_claimed_job(claim_jobs()[0]))
        self.assertEqual(RecipientLog.objects.get(campaign=blast).error_message, SKIPPED_MESSAGE)

    @patch("apps.mail.services.campaign.send.runner._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    def test_manual_hold_while_in_process_sender_waits(self, transport, _client):
        def enter(*, before_provider_call, **_kwargs):
            suppress(self.address)
            before_provider_call()
            self.fail("Transport crossed the provider boundary")

        transport.side_effect = enter
        _make_active_aws()
        EmailServiceConfig.objects.create(is_active=True, from_email="sender@example.org")
        blast = campaign(audience_type="manual", manual_emails=self.address)
        send_campaign(blast, make_superuser())
        self.assertEqual(RecipientLog.objects.get(campaign=blast).error_message, SKIPPED_MESSAGE)
