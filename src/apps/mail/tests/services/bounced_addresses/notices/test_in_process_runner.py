from unittest.mock import MagicMock, Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail
from apps.core.models import BackgroundJob, EmailServiceConfig
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.event.tests.helpers import make_superuser
from apps.mail.models import BouncedAddress, RecipientLog
from apps.mail.services.audience import get_recipients
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.send_campaign import SesSendResult
from apps.mail.services.send_campaign.runner import send_campaign, send_to_recipients
from apps.mail.services.suppression import SKIPPED_MESSAGE
from apps.mail.tests.services.bounced_addresses.notices.test_send_path import _make_active_aws, campaign, suppress

from ..helpers import make_person


@patch("apps.mail.services.send_campaign.runner._get_ses_client", return_value=MagicMock())
@patch("apps.mail.services.send_campaign.runner._send_via_ses", return_value=SesSendResult(message_id="SES-1"))
class InProcessRunnerTests(TestCase):
    """Background jobs off: the in-process runner."""

    def setUp(self):
        cache.clear()
        _make_active_aws()
        EmailServiceConfig.objects.create(is_active=True, from_email="noreply@example.org", from_name="I2G")
        self.sender = make_superuser()
        ContactEmail.objects.filter(member=self.sender).update(subscribe=False)  # not in the audience itself
        make_person("alice@example.org", first="Alice")
        make_person("bob@example.org", first="Bob")
        self.campaign = campaign(audience_type="subscribers")

    def sent_to(self, send) -> list:
        return sorted(call.kwargs["recipient"] for call in send.call_args_list)

    def test_a_suppressed_address_gets_no_recipient_log_and_no_message(self, send, _client):
        suppress("bob@example.org")

        send_campaign(self.campaign, self.sender)

        self.assertEqual(self.sent_to(send), ["alice@example.org"])
        self.assertFalse(RecipientLog.objects.filter(email_address="bob@example.org").exists())
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.sent_count), ("sent", 1))

    def test_an_address_suppressed_after_the_audience_was_resolved_is_skipped(self, send, _client):
        resolved = get_recipients(self.campaign)
        suppress("bob@example.org")

        with patch("apps.mail.services.send_campaign.runner.get_recipients", return_value=resolved):
            send_campaign(self.campaign, self.sender)

        self.assertEqual(self.sent_to(send), ["alice@example.org"])
        log = RecipientLog.objects.get(email_address="bob@example.org")
        self.assertEqual((log.status, log.error_message), ("failed", SKIPPED_MESSAGE))
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.failed_count), ("partial", 1))

    def test_resumed_paused_recipients_are_checked_again(self, send, _client):
        log = RecipientLog.objects.create(
            campaign=self.campaign, email_address="bob@example.org", recipient_name="Bob", status="pending"
        )
        suppress("bob@example.org")
        recipient = {
            "member_id": None,
            "email": "bob@example.org",
            "first_name": "Bob",
            "last_name": "",
            "full_name": "Bob",
        }

        send_to_recipients(self.campaign, [(recipient, log)])

        send.assert_not_called()
        log.refresh_from_db()
        self.assertEqual((log.status, log.error_message), ("failed", SKIPPED_MESSAGE))


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class QueuedJobTests(TestCase):
    """Background jobs on: one durable job per recipient."""

    def setUp(self):
        cache.clear()
        self.sender = make_superuser()

    def queued(self, manual):
        item = campaign(audience_type="manual", manual_emails=manual)
        queue_email_campaign(item, sent_by=self.sender)
        return item

    def test_queueing_leaves_suppressed_addresses_out(self):
        suppress("blocked@example.org")

        item = self.queued("blocked@example.org\nopen@example.org")

        self.assertEqual(
            list(RecipientLog.objects.filter(campaign=item).values_list("email_address", flat=True)),
            ["open@example.org"],
        )
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.email_recipient").count(), 1)

    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
    def test_a_job_queued_before_the_suppression_sends_nothing(self, send):
        item = self.queued("late@example.org")
        suppress("late@example.org")
        job = claim_jobs()[0]

        self.assertTrue(process_claimed_job(job))

        send.assert_not_called()
        job.refresh_from_db()
        log = RecipientLog.objects.get(campaign=item)
        item.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual((log.status, log.error_message), ("failed", SKIPPED_MESSAGE))
        self.assertEqual((item.status, item.failed_count), ("failed", 1))

    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses", return_value=SesSendResult(message_id="x"))
    def test_a_cleared_address_is_sent_again(self, send, load_config, *_mocks):
        load_config.return_value = Mock(source_address="I2G <noreply@example.org>", ses_configuration_set_name="")
        row = suppress("back@example.org")
        BouncedAddress.objects.filter(pk=row.pk).update(suppressed_at=None, suppression="")
        self.queued("back@example.org")

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        self.assertEqual(send.call_args.kwargs["recipient"], "back@example.org")


class TransactionalMailTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.authn.services.email.send_email.transport.deliver_email")
    def test_notifications_and_codes_still_reach_a_suppressed_address(self, deliver):
        from apps.authn.services.email.send_email import send_notification_email

        suppress("notified@example.org")
        config = Mock(delivery_configured=True)

        with patch("apps.authn.services.email.send_email._load_config", return_value=config):
            sent = send_notification_email(
                recipient="notified@example.org",
                subject="Security notice",
                template="authn/email/email_claim_notification.html",
                context={"account_url": ""},
            )

        self.assertTrue(sent)
        self.assertEqual(deliver.call_args.args[0].to, ("notified@example.org",))
