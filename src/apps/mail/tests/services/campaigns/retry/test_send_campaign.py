"""The legacy in-process retry sender has the same final policy and method-snapshot guarantees."""

from unittest.mock import patch

from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.event.tests.helpers import make_member
from apps.mail.models import RecipientLog
from apps.mail.services.campaign.send.runner import send_campaign
from apps.mail.services.campaign.send.transport import SesSendResult
from apps.mail.tests.services.campaigns.retry.helpers import make_retry_campaign
from apps.mail.tests.services.campaigns.send.test_send_campaign_runner import _make_active_aws


class RetryInProcessSendTests(TestCase):
    def setUp(self):
        _make_active_aws()
        self.sender = make_member(email="retry-runner@example.org")

    @patch("apps.mail.services.campaign.send.runner._get_ses_client", side_effect=lambda config: config)
    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    def test_live_change_at_before_provider_callback_blocks_in_process_send(self, send, _get_client):
        retry, _source, member, _row, _config = make_retry_campaign()
        provider_touched = False

        def change_then_enter_provider(*, before_provider_call, **_kwargs):
            nonlocal provider_touched
            ContactEmail.objects.filter(member=member, email_address=retry.retry_address).update(verified=False)
            before_provider_call()
            provider_touched = True
            return SesSendResult(message_id="must-not-send")

        send.side_effect = change_then_enter_provider
        result = send_campaign(retry, self.sender)

        log = RecipientLog.objects.get(campaign=retry)
        self.assertFalse(provider_touched)
        self.assertEqual(result, {"total": 1, "sent": 0, "failed": 1})
        self.assertEqual(log.status, "failed")
        self.assertFalse(log.provider_message_id)

    @patch("apps.mail.services.campaign.send.runner._get_ses_client", side_effect=lambda config: config)
    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    def test_in_process_send_uses_snapshot_after_global_switch(self, send, _get_client):
        retry, _source, _member, _row, config = make_retry_campaign()
        config.provider = "smtp"
        config.from_email = "global-now@example.org"
        config.from_name = "Global now"
        config.save(update_fields=["provider", "from_email", "from_name", "updated_at"])

        def accept(*, before_provider_call, **_kwargs):
            before_provider_call()
            return SesSendResult(message_id="snapshot-send", provider="ses")

        send.side_effect = accept
        send_campaign(retry, self.sender)

        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs["ses_client"].provider, "ses")
        self.assertEqual(kwargs["source"], "I2G <snapshot@example.org>")
        self.assertEqual(kwargs["configuration_set"], "retry-config-set")
