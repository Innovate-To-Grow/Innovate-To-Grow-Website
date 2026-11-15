from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.core.models import (
    AWSCredentialConfig,
    SMTPProviderConfig,
)
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.services.send_campaign.transport import (
    SesSendResult,
)
from apps.mail.tests.services.campaigns.send_providers.test_send_campaign_provider_neutral import (
    AWS_SECRET,
    RUNNER_LOGGER,
    create_graph_sender,
)


class SesTrackingWarningTests(TestCase):
    """The 'no SES configuration set' warning concerns SES bounce tracking, so only SES campaigns may log it."""

    def setUp(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key=AWS_SECRET,
            default_region="us-west-2",
        )
        SMTPProviderConfig.objects.create(name="SMTP", is_active=True, host="smtp.example.com", port=587)
        self.config = create_graph_sender()
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        make_member(email="alice@example.com", first_name="Alice", last_name="Smith")

    def run_campaign(self, provider):
        self.config.provider = provider
        self.config.save()
        campaign = EmailCampaign.objects.create(
            subject="Hi", body="<p>Hello</p>", audience_type="subscribers", member_email_scope="primary", status="draft"
        )
        result = SesSendResult(message_id="ID-1", provider=provider)
        with patch(f"{RUNNER_LOGGER}._send_via_ses", return_value=result):
            return send_campaign(campaign, self.sender), campaign

    @override_settings(SES_CONFIGURATION_SET_NAME="")
    def test_ses_campaign_without_a_configuration_set_warns_that_tracking_is_disabled(self):
        with self.assertLogs(RUNNER_LOGGER, level="WARNING") as logs:
            summary, campaign = self.run_campaign("ses")

        self.assertEqual(summary, {"total": 2, "sent": 2, "failed": 0})
        self.assertEqual(len(logs.records), 1)
        self.assertIn("No SES configuration set configured", logs.output[0])
        self.assertIn(str(campaign.pk), logs.output[0])

    @override_settings(SES_CONFIGURATION_SET_NAME="tracking-set")
    def test_ses_campaign_with_a_configuration_set_does_not_warn(self):
        with self.assertNoLogs(RUNNER_LOGGER, level="WARNING"):
            summary, _ = self.run_campaign("ses")

        self.assertEqual(summary["sent"], 2)

    @override_settings(SES_CONFIGURATION_SET_NAME="")
    def test_graph_and_smtp_campaigns_never_warn_about_ses_tracking(self):
        for provider in ("graph", "smtp"):
            with self.subTest(provider=provider), self.assertNoLogs(RUNNER_LOGGER, level="WARNING"):
                summary, campaign = self.run_campaign(provider)

                campaign.refresh_from_db()
                self.assertEqual((summary["sent"], campaign.status), (2, "sent"))
