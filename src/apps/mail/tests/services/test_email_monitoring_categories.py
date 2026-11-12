"""Every kind of mail the site sends is recorded by the email telemetry, under its own category.

The real senders and the real Microsoft Graph provider run; only ``graph.transport.post`` is replaced, as in
``test_sending_method_reaches_all_mail``. Campaign recipients sent by the background worker are filed under their
campaign, and every retry of a recipient's job is one more attempt of the same logical email.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.services.email import send_admin_invitation_email, send_notification_email, send_verification_email
from apps.core.models import BackgroundJob, EmailCategory, EmailServiceConfig, OutboundEmail
from apps.core.services.background_jobs import claim_jobs
from apps.core.services.background_jobs.worker import run_claimed_job
from apps.core.services.delivery_rates.families import clear_gate_cache
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.delivery_rates.helpers import FakeClock
from apps.event.services.ticket.mail import send_ticket_email
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.inbox.reply import send_reply
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.tests.services.send_campaign.test_send_campaign_provider_neutral import (
    FakeGraphTransport,
    ScriptedGraphTransport,
)

SENDER = "i2g@ucmerced.edu"


class GraphMailTestCase(TestCase):
    def setUp(self):
        cache.clear()
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.addCleanup(clear_gate_cache)
        self.clock = FakeClock(timezone.now()).install(self)
        self.superuser = make_superuser()
        create_graph_config(scope=(SENDER,), name="Graph", is_active=True, mailbox=SENDER)
        self.config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="graph", from_email=SENDER, from_name="Innovate to Grow"
        )

    def use_transport(self, transport):
        patcher = patch("apps.core.services.email.graph.transport.post", transport)
        patcher.start()
        self.addCleanup(patcher.stop)
        return transport


class EveryKindOfMailTests(GraphMailTestCase):
    def test_each_sender_files_its_email_under_its_category(self):
        self.use_transport(FakeGraphTransport())
        self.client.force_login(self.superuser)
        event = make_event()
        registration = make_registration(
            make_member(email="guest@example.com"), event, make_ticket(event), attendee_email="guest@example.com"
        )
        invitation = SimpleNamespace(
            pk="invitation-1",
            email="invitee@example.com",
            get_acceptance_url=lambda request: "https://i2g.example.edu/admin/accept/token/",
            expires_at=timezone.now(),
            invited_by=self.superuser,
            message="",
            get_role_display=lambda: "Staff",
        )

        send_verification_email(recipient="code@example.com", code="123456", purpose="login")
        send_verification_email(recipient="reset@example.com", code="654321", purpose="password_reset")
        send_verification_email(recipient="join@example.com", code="111111", purpose="register")
        send_notification_email(
            recipient="notice@example.com",
            subject="Notice",
            template="authn/email/email_claim_notification.html",
            context={},
        )
        send_admin_invitation_email(invitation=invitation)
        send_ticket_email(registration)
        self.assertEqual(send_reply(to_email="replied@example.com", subject="Re: hi", reply_body="Thanks"), "")
        self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"})

        categories = dict(OutboundEmail.objects.values_list("recipient", "category"))
        self.assertEqual(
            categories,
            {
                "code@example.com": EmailCategory.SIGN_IN,
                "reset@example.com": EmailCategory.PASSWORD,
                "join@example.com": EmailCategory.VERIFICATION,
                "notice@example.com": EmailCategory.NOTIFICATION,
                "invitee@example.com": EmailCategory.INVITATION,
                "guest@example.com": EmailCategory.EVENT_TICKET,
                "replied@example.com": EmailCategory.INBOX_REPLY,
                "ops@example.com": EmailCategory.TEST,
            },
        )
        self.assertEqual(set(OutboundEmail.objects.values_list("status", "delivery_status")), {("accepted", "unknown")})
        code = OutboundEmail.objects.get(recipient="code@example.com")
        self.assertEqual((code.subcategory, code.send_format), ("login", "json"))
        self.assertNotIn("123456", code.subject)
        ticket = OutboundEmail.objects.get(recipient="guest@example.com")
        self.assertEqual((ticket.source_type, ticket.source_id), ("event.eventregistration", str(registration.pk)))

    def test_an_in_process_campaign_files_every_recipient_under_the_campaign(self):
        self.use_transport(FakeGraphTransport())
        campaign = EmailCampaign.objects.create(
            name="News",
            subject="News",
            body="<p>x</p>",
            audience_type="manual",
            manual_emails="a@example.com\nb@example.com",
        )

        send_campaign(campaign, self.superuser)

        emails = OutboundEmail.objects.filter(campaign_id=campaign.pk)
        self.assertEqual(sorted(emails.values_list("recipient", flat=True)), ["a@example.com", "b@example.com"])
        self.assertEqual(set(emails.values_list("category", "source_type")), {("campaign", "mail.recipientlog")})
        log = RecipientLog.objects.get(campaign=campaign, email_address="a@example.com")
        self.assertEqual(emails.get(recipient="a@example.com").source_id, str(log.pk))


class CampaignJobRetryTests(GraphMailTestCase):
    def test_a_recipient_job_that_is_throttled_then_accepted_is_one_email_with_two_attempts(self):
        throttled = HttpResponse(429, {"retry-after": "5", "request-id": "req-throttle-0001"}, b"")
        self.use_transport(ScriptedGraphTransport(throttled, HttpResponse(202, {}, b"")))
        campaign = EmailCampaign.objects.create(
            name="Queued",
            subject="Hello",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=self.superuser)

        for _round in range(2):
            for job in claim_jobs():
                run_claimed_job(job)
            # Past Microsoft's Retry-After for the limiter, and due again for the worker.
            self.clock.advance(3600)
            clear_gate_cache()
            BackgroundJob.objects.filter(status="retry").update(available_at=timezone.now())

        email = OutboundEmail.objects.get(campaign_id=campaign.pk)
        attempts = list(email.attempts.order_by("attempt_number").values_list("http_status", "outcome", "job_attempt"))
        self.assertEqual(attempts, [(429, "transient", 1), (202, "accepted", 2)])
        self.assertEqual((email.status, email.attempt_count), ("accepted", 2))
        self.assertIsNotNone(email.job_id)
        self.assertEqual(RecipientLog.objects.get(campaign=campaign).status, "sent")
