from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.core.models import (
    MicrosoftGraphProviderConfig,
)
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import HttpResponse
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.send.runner import _configured_provider, send_campaign
from apps.mail.tests.services.campaigns.send_providers.test_send_campaign_provider_neutral import (
    DENIED_BODY,
    GRAPH_LOGGER,
    LEAKS,
    POST,
    RUNNER_LOGGER,
    FakeGraphTransport,
    ScriptedGraphTransport,
    create_graph_sender,
    posted_mime,
)


@override_settings(BACKEND_URL="https://backend.example.com")
class GraphCampaignRunTests(TestCase):
    """A whole ``send_campaign`` run through the real Graph provider."""

    def setUp(self):
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.config = create_graph_sender()
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        make_member(email="alice@example.com", first_name="Alice", last_name="Smith")
        make_member(email="bob@example.com", first_name="Bob", last_name="Jones")
        self.campaign = EmailCampaign.objects.create(
            subject="Hi {{first_name}}",
            body="<p>Hello</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
        )

    def logs_by_recipient(self):
        return {log.email_address: log for log in RecipientLog.objects.filter(campaign=self.campaign)}

    def test_campaign_is_delivered_through_graph_with_unsubscribe_headers_and_no_ses_tags(self):
        transport = FakeGraphTransport()

        with patch(POST, transport):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 3, "failed": 0})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sent")
        self.assertEqual(len(transport.sent), 3)
        self.assertEqual(len(transport.token_requests), 1)
        logs = self.logs_by_recipient()
        for call in transport.sent:
            mime = posted_mime(call)
            log = logs[str(mime["To"])]
            self.assertEqual(call.path, "/v1.0/users/mailer@example.com/sendMail")
            self.assertEqual((log.provider, log.status, log.error_message), ("graph", "sent", ""))
            self.assertEqual(log.provider_message_id, mime["Message-ID"])
            self.assertIsNone(mime["X-SES-MESSAGE-TAGS"])
            self.assertTrue(mime["List-Unsubscribe"].startswith("<https://backend.example.com/mail/unsubscribe/"))
            self.assertEqual(mime["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertEqual(len({log.provider_message_id for log in logs.values()}), 3)

    def test_graph_rejection_stops_the_campaign_and_pauses_the_rest_until_resumed(self):
        # Microsoft refusing to let the app send as the mailbox stops Graph sending (a breaker). The runner waits
        # out its first timed probe (as long as waits.dedicated_seconds allows), which is refused too; the breaker
        # then stays open for longer, so the last recipient is paused instead of failing.
        transport = FakeGraphTransport(HttpResponse(403, {}, DENIED_BODY.encode()))

        with self.assertLogs(GRAPH_LOGGER, level="WARNING") as captured, patch(POST, transport):
            send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.failed_count), ("partial", 2))
        self.assertEqual(len(transport.sent), 2)
        logs = list(self.logs_by_recipient().values())
        failed = [log for log in logs if log.status == "failed"]
        self.assertEqual([log.status for log in logs if log not in failed], ["paused"])
        for log in failed:
            self.assertEqual((log.provider, log.provider_message_id), ("graph", ""))
            self.assertEqual(log.error_message, "Microsoft Graph rejected the request (ErrorSendAsDenied).")
        for leaked in LEAKS:
            self.assertNotIn(leaked, "\n".join(captured.output))

    def test_a_throttled_recipient_is_sent_again_after_the_retry_after_and_never_failed(self):
        transport = ScriptedGraphTransport(
            HttpResponse(429, {"retry-after": "30"}, DENIED_BODY.encode()), HttpResponse(202, {}, b"")
        )

        with self.assertLogs(GRAPH_LOGGER, level="WARNING"), patch(POST, transport):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 3, "failed": 0})
        self.assertEqual(len(transport.sent), 4)
        first, second = transport.sent[:2]
        self.assertEqual(posted_mime(first)["To"], posted_mime(second)["To"])

    def test_recipients_throttled_every_time_are_paused_not_failed(self):
        # Each 429 cools Graph down for its Retry-After; the runner waits that out and sends again, until the
        # throttles in a row reach controller.persistent_throttle_count and the rest is left for "Resume paused".
        transport = FakeGraphTransport(HttpResponse(429, {"retry-after": "30"}, DENIED_BODY.encode()))

        with self.assertLogs(GRAPH_LOGGER, level="WARNING"), patch(POST, transport):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 0, "failed": 0})
        self.assertEqual(len(transport.sent), settings.DELIVERY_RATES["controller"]["persistent_throttle_count"])
        self.assertEqual({log.status for log in self.logs_by_recipient().values()}, {"paused"})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "partial")

    def test_graph_selected_without_active_graph_credentials_fails_before_anything_is_sent(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)
        transport = FakeGraphTransport()

        with patch(POST, transport), self.assertRaisesMessage(RuntimeError, "Email delivery is not configured"):
            send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")
        self.assertEqual(transport.calls, [])
        for log in self.logs_by_recipient().values():
            self.assertEqual((log.status, log.provider), ("failed", ""))

    def test_unexpected_errors_record_graph_as_the_configured_provider(self):
        transport = FakeGraphTransport()
        self.assertEqual(_configured_provider(self.config), "graph")

        with (
            patch(POST, transport),
            patch(f"{RUNNER_LOGGER}.personalize", side_effect=RuntimeError("boom")),
            self.assertLogs(RUNNER_LOGGER, level="ERROR"),
        ):
            summary = send_campaign(self.campaign, self.sender)

        self.assertEqual(summary, {"total": 3, "sent": 0, "failed": 3})
        self.assertEqual(transport.calls, [])
        for log in self.logs_by_recipient().values():
            self.assertEqual((log.provider, log.status), ("graph", "failed"))
