"""Manual Emails recipients get the member's personal {{login_link}}, or the sign-in page when they have no account."""

import re
from unittest.mock import MagicMock, Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail
from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import EmailCampaign, LoginLinkToken, RecipientLog
from apps.mail.services.audience import get_recipients
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.campaign.dispatch.email_job import _render_recipient_email
from apps.mail.services.campaign.preview import HTML_MARKER
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.services.send_campaign.transport import SesSendResult

FRONTEND = "https://i2g.example"
SIGN_IN_PAGE = f"{FRONTEND}/login"
TOKEN_LINK = re.compile(re.escape(f"{FRONTEND}/login-link#token=") + r"[A-Za-z0-9_\-]+")
PLAIN_BODY = "This is a test of the login link in email blasts.\n{{login_link}}"
HTML_BODY = f'{HTML_MARKER}<p>Hi {{{{first_name}}}}, <a href="{{{{login_link}}}}">sign in</a></p>'


def _manual_campaign(manual_emails, *, subject="I2G test: login link", body=PLAIN_BODY):
    return EmailCampaign.objects.create(
        name="Manual login link",
        subject=subject,
        body=body,
        audience_type="manual",
        manual_emails=manual_emails,
        status="draft",
    )


def _make_active_aws():
    AWSCredentialConfig.objects.all().delete()
    AWSCredentialConfig.objects.create(
        name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
    )


class ManualAudienceMemberMatchTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="hong@example.edu", first_name="Hong", last_name="Xie")
        ContactEmail.objects.create(member=self.member, email_address="hong.alt@example.org", email_type="secondary")

    def test_an_address_of_a_member_resolves_to_that_member_in_any_case(self):
        campaign = _manual_campaign("HONG@Example.edu\n  hong.alt@EXAMPLE.org  ")

        recipients = get_recipients(campaign)

        self.assertEqual([recipient["email"] for recipient in recipients], ["HONG@Example.edu", "hong.alt@EXAMPLE.org"])
        for recipient in recipients:
            self.assertEqual(recipient["member_id"], self.member.pk)
            self.assertEqual(recipient["first_name"], "Hong")
            self.assertEqual(recipient["last_name"], "Xie")
            self.assertEqual(recipient["full_name"], "Hong Xie")

    def test_unknown_inactive_and_ownerless_addresses_stay_without_a_member(self):
        inactive = make_member(email="gone@example.edu", first_name="Gone", last_name="Away")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        ContactEmail.objects.create(member=None, email_address="ownerless@example.edu")
        campaign = _manual_campaign("stranger@example.edu\ngone@example.edu\nownerless@example.edu")

        recipients = get_recipients(campaign)

        self.assertEqual(len(recipients), 3)
        for recipient in recipients:
            self.assertIsNone(recipient["member_id"])
            self.assertEqual(recipient["full_name"], "")

    def test_lines_are_deduplicated_case_insensitively_keeping_the_first_spelling(self):
        campaign = _manual_campaign("Hong@Example.edu\nhong@example.edu\n\nother@example.edu\nOTHER@example.edu\n")

        recipients = get_recipients(campaign)

        self.assertEqual([recipient["email"] for recipient in recipients], ["Hong@Example.edu", "other@example.edu"])

    def test_the_whole_list_is_matched_in_one_query(self):
        campaign = _manual_campaign(
            "\n".join(f"person{index}@example.edu" for index in range(25)) + "\nhong@example.edu"
        )

        # One query matches every address to its member; one more reads the bulk-mail suppression list (Email
        # Monitoring → Bounced addresses). Neither grows with the list.
        with self.assertNumQueries(2):
            recipients = get_recipients(campaign)

        self.assertEqual(recipients[-1]["member_id"], self.member.pk)


@override_settings(FRONTEND_URL=f"{FRONTEND}/")
@patch("apps.mail.services.send_campaign.runner._send_via_ses", return_value=SesSendResult(message_id="SES-1"))
@patch("apps.mail.services.send_campaign.runner._get_ses_client", return_value=MagicMock())
class ManualCampaignRunnerLoginLinkTests(TestCase):
    """The in-process runner (background jobs off)."""

    def setUp(self):
        cache.clear()
        _make_active_aws()
        EmailServiceConfig.objects.create(
            is_active=True, from_email="i2g@example.edu", from_name="I2G", max_send_rate=0
        )
        self.sender = make_superuser()
        self.member = make_member(email="hongxie@example.edu", first_name="Hong", last_name="Xie")

    def _sent(self, send):
        self.assertEqual(send.call_count, 1)
        return send.call_args.kwargs

    def test_the_production_report_a_plain_text_test_to_a_member_carries_a_working_login_link(self, _client, send):
        campaign = _manual_campaign("HongXie@Example.edu")

        send_campaign(campaign, self.sender)

        sent = self._sent(send)
        token = LoginLinkToken.objects.get(campaign=campaign, member=self.member)
        link = f"{FRONTEND}/login-link#token={token.token}"
        self.assertEqual(sent["subject"], "I2G test: login link")
        self.assertIn("This is a test of the login link in email blasts.", sent["html_body"])
        self.assertIn(f'<a href="{link}" style="color:#0f2d52;">{link}</a>', sent["html_body"])
        self.assertIs(sent["keep_sent_copy"], False)
        self.assertEqual(RecipientLog.objects.get(campaign=campaign).member_id, self.member.pk)

    def test_an_html_body_to_a_member_gets_the_link_and_the_name(self, _client, send):
        campaign = _manual_campaign("hongxie@example.edu", body=HTML_BODY)

        send_campaign(campaign, self.sender)

        sent = self._sent(send)
        self.assertRegex(sent["html_body"], r'<p>Hi Hong, <a href="' + TOKEN_LINK.pattern + '">sign in</a></p>')
        self.assertIs(sent["keep_sent_copy"], False)

    def test_an_address_without_an_account_gets_the_sign_in_page_and_keeps_its_sent_copy(self, _client, send):
        campaign = _manual_campaign("stranger@example.edu")

        send_campaign(campaign, self.sender)

        sent = self._sent(send)
        self.assertIn(f'<a href="{SIGN_IN_PAGE}" style="color:#0f2d52;">{SIGN_IN_PAGE}</a>', sent["html_body"])
        self.assertIs(sent["keep_sent_copy"], True)
        self.assertFalse(LoginLinkToken.objects.filter(campaign=campaign).exists())

    def test_an_inactive_member_gets_the_sign_in_page_and_no_token(self, _client, send):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        campaign = _manual_campaign("hongxie@example.edu", body=HTML_BODY)

        send_campaign(campaign, self.sender)

        sent = self._sent(send)
        self.assertIn(f'<a href="{SIGN_IN_PAGE}">sign in</a>', sent["html_body"])
        self.assertNotIn("/login-link", sent["html_body"])
        self.assertIs(sent["keep_sent_copy"], True)
        self.assertFalse(LoginLinkToken.objects.exists())


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
