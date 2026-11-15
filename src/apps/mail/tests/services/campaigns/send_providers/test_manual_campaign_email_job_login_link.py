from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import LoginLinkToken, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.campaign.dispatch.email_job import _render_recipient_email
from apps.mail.services.send_campaign.transport import SesSendResult
from apps.mail.tests.services.campaigns.send.test_manual_login_link import (
    FRONTEND,
    HTML_BODY,
    PLAIN_BODY,
    SIGN_IN_PAGE,
    TOKEN_LINK,
    _manual_campaign,
)


@override_settings(FRONTEND_URL=FRONTEND, BACKGROUND_JOBS_ENABLED=True)
class ManualCampaignEmailJobLoginLinkTests(TestCase):
    """The durable background job, which rebuilds the recipient's context from the recipient log."""

    def setUp(self):
        cache.clear()
        self.sender = make_superuser()
        self.member = make_member(email="hongxie@example.edu", first_name="Hong", last_name="Xie")

    def _queued(self, manual_emails, body=PLAIN_BODY):
        campaign = _manual_campaign(manual_emails, body=body)
        queue_email_campaign(campaign, sent_by=self.sender)
        return campaign, RecipientLog.objects.select_related("campaign", "member").get(campaign=campaign)

    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses", return_value=SesSendResult(message_id="x"))
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    def test_a_member_gets_the_login_link_through_the_job(self, _client, send):
        campaign, log = self._queued("HONGXIE@example.edu")
        self.assertEqual(log.member_id, self.member.pk)

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        sent = send.call_args.kwargs
        token = LoginLinkToken.objects.get(campaign=campaign, member=self.member)
        link = f"{FRONTEND}/login-link#token={token.token}"
        self.assertEqual(sent["recipient"], "HONGXIE@example.edu")
        self.assertIn(f'<a href="{link}" style="color:#0f2d52;">{link}</a>', sent["html_body"])
        self.assertIs(sent["keep_sent_copy"], False)

    def test_an_html_body_renders_the_link_and_name_for_a_member(self):
        _campaign, log = self._queued("hongxie@example.edu", body=HTML_BODY)

        subject, html, _unsubscribe, keep_sent_copy = _render_recipient_email(log)

        self.assertEqual(subject, "I2G test: login link")
        self.assertRegex(html, r'<p>Hi Hong, <a href="' + TOKEN_LINK.pattern + '">sign in</a></p>')
        self.assertIs(keep_sent_copy, False)

    def test_an_address_without_an_account_gets_the_sign_in_page(self):
        campaign, log = self._queued("stranger@example.edu")

        _subject, html, _unsubscribe, keep_sent_copy = _render_recipient_email(log)

        self.assertIn(f'<a href="{SIGN_IN_PAGE}" style="color:#0f2d52;">{SIGN_IN_PAGE}</a>', html)
        self.assertIs(keep_sent_copy, True)
        self.assertFalse(LoginLinkToken.objects.filter(campaign=campaign).exists())
