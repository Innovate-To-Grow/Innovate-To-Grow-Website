"""Switching Email Sending Method moves every email the site sends.

Each sender reads the active ``EmailServiceConfig`` when it sends, so after **Use for email** every kind of mail
(sign-in codes, notifications, admin invitations, tickets, campaigns, inbox replies and the admin test email) goes
through the new method and none through the old one. The real providers run; only their transports are replaced
(boto3 for SES, ``smtplib`` for SMTP, ``graph.transport.post`` for Microsoft Graph), so nothing reaches a network.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.services.email import send_admin_invitation_email, send_notification_email, send_verification_email
from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig
from apps.core.services.background_jobs import claim_jobs
from apps.core.services.background_jobs.worker import run_claimed_job
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.delivery_rates.helpers import FakeClock
from apps.event.services.ticket.mail import send_ticket_email
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.inbox.reply import send_reply
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.tests.services.send_campaign.test_send_campaign_provider_neutral import FakeGraphTransport, posted_mime

SENDER = "mailer@example.com"
# One recipient per kind of mail, so each send can be traced to the flow that made it.
FLOW_RECIPIENTS = {
    "sign-in code": "code@example.com",
    "notification": "notice@example.com",
    "admin invitation": "invitee@example.com",
    "ticket": "guest@example.com",
    "inbox reply": "replied@example.com",
    "admin test email": "ops@example.com",
}


class Transports:
    """Every provider's transport, recording the recipients each one was handed."""

    def __init__(self, test):
        ses = patch("apps.core.services.email.ses.boto3.client").start()
        ses.return_value.send_raw_email.return_value = {"MessageId": "ses-1"}
        self.ses = ses.return_value.send_raw_email
        smtp = patch("apps.core.services.email.smtp.smtplib.SMTP").start()
        smtp.return_value.send_message.return_value = {}
        self.smtp = smtp.return_value.send_message
        self.graph = FakeGraphTransport()
        patch("apps.core.services.email.graph.transport.post", self.graph).start()
        test.addCleanup(patch.stopall)

    def recipients(self, provider) -> list[str]:
        if provider == "ses":
            calls = self.ses.call_args_list
            return [address for call in calls for address in call.kwargs["Destinations"]]
        if provider == "smtp":
            return [address for call in self.smtp.call_args_list for address in call.kwargs["to_addrs"]]
        return [address for call in self.graph.sent for address in _graph_recipients(call)]


def _graph_recipients(call) -> list[str]:
    """A sendMail request's To addresses: MIME (base64), or the JSON message used for mail that keeps no Sent copy."""
    if call.headers.get("Content-Type", "").startswith("application/json"):
        message = json.loads(call.body)["message"]
        return [recipient["emailAddress"]["address"] for recipient in message["toRecipients"]]
    return [str(posted_mime(call)["To"])]


class SendingMethodReachesAllMailTests(TestCase):
    def setUp(self):
        cache.clear()
        clear_access_token_cache()
        FakeClock(timezone.now()).install(self)
        self.transports = Transports(self)
        self.superuser = make_superuser()
        self.client.force_login(self.superuser)
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        SMTPProviderConfig.objects.create(
            name="SMTP", is_active=True, host="smtp.example.com", port=587, username="mailer", password="pw"
        )
        create_graph_config(scope=(SENDER,), name="Outlook", is_active=True, mailbox=SENDER)
        self.config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email=SENDER, from_name="Innovate to Grow"
        )
        event = make_event()
        self.registration = make_registration(
            make_member(email=FLOW_RECIPIENTS["ticket"]),
            event,
            make_ticket(event),
            attendee_email=FLOW_RECIPIENTS["ticket"],
        )
        self.campaign = EmailCampaign.objects.create(
            subject="News",
            body="<p>Hello</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
        )

    def use_for_email(self, provider):
        self.client.post(reverse("admin:mail_settings_use_provider", args=[provider]))
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, provider)

    def send_every_kind_of_mail(self):
        send_verification_email(recipient=FLOW_RECIPIENTS["sign-in code"], code="123456", purpose="login")
        send_notification_email(
            recipient=FLOW_RECIPIENTS["notification"],
            subject="Notice",
            template="authn/email/email_claim_notification.html",
            context={},
        )
        invitation = SimpleNamespace(
            email=FLOW_RECIPIENTS["admin invitation"],
            get_acceptance_url=lambda request: "https://i2g.example.edu/admin/accept/token/",
            expires_at=timezone.now(),
            invited_by=self.superuser,
            message="",
            get_role_display=lambda: "Staff",
        )
        send_admin_invitation_email(invitation=invitation)
        send_ticket_email(self.registration)
        self.assertEqual(send_reply(to_email=FLOW_RECIPIENTS["inbox reply"], subject="Re: hi", reply_body="Thanks"), "")
        self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": FLOW_RECIPIENTS["admin test email"]})
        send_campaign(self.campaign, self.superuser)
        return set(RecipientLog.objects.filter(campaign=self.campaign).values_list("email_address", flat=True))

    def assert_all_mail_went_through(self, provider, *, not_through):
        campaign_recipients = self.send_every_kind_of_mail()

        sent = self.transports.recipients(provider)
        for flow, recipient in FLOW_RECIPIENTS.items():
            self.assertIn(recipient, sent, f"{flow} did not go through {provider}")
        self.assertTrue(campaign_recipients)
        self.assertLessEqual(campaign_recipients, set(sent), "the campaign did not go through {provider}")
        self.assertEqual(
            RecipientLog.objects.filter(campaign=self.campaign).exclude(status="sent").count(),
            0,
            "a campaign send failed",
        )
        for other in not_through:
            self.assertEqual(self.transports.recipients(other), [], f"mail still went through {other}")

    def test_switching_from_ses_to_smtp_moves_all_mail_to_smtp(self):
        self.use_for_email("smtp")

        self.assert_all_mail_went_through("smtp", not_through=("ses", "graph"))

    def test_switching_from_ses_to_microsoft_graph_moves_all_mail_to_graph(self):
        self.use_for_email("graph")

        self.assert_all_mail_went_through("graph", not_through=("ses", "smtp"))

    def test_switching_back_to_ses_moves_all_mail_back(self):
        self.use_for_email("graph")
        self.use_for_email("ses")

        self.assert_all_mail_went_through("ses", not_through=("smtp", "graph"))

    def test_a_campaign_queued_before_the_switch_goes_out_through_the_new_method(self):
        # Production can send campaigns from the background worker: each recipient's job reads the method as it runs.
        campaign = EmailCampaign.objects.create(
            name="Queued",
            subject="Hello",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=self.superuser)
        self.use_for_email("smtp")

        jobs = claim_jobs()
        for job in jobs:
            run_claimed_job(job)

        self.assertTrue(jobs)
        self.assertEqual(self.transports.recipients("smtp"), ["worker@example.com"])
        self.assertEqual(self.transports.recipients("ses"), [])
        self.assertEqual(RecipientLog.objects.get(campaign=campaign).status, "sent")
