"""The in-process campaign sender (used while background jobs are off) uses the shared, provider-wide schedule."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.tests.graph_helpers import create_graph_config
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.services.send_campaign.transport import SesSendResult

# Graph senders used in this module; the mailbox scope rules have their own tests.
GRAPH_TEST_SCOPE = ("noreply@example.com", "admin@example.com")

TENANT_ID = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@patch("apps.mail.services.send_campaign.runner.wait_for_delivery_slot", return_value=0.0)
@patch("apps.mail.services.send_campaign.runner._send_via_ses", return_value=SesSendResult(message_id="id"))
@patch("apps.mail.services.send_campaign.runner._get_ses_client", return_value=MagicMock())
class RunnerSendRateTests(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        make_member(email="alice@example.com", first_name="Alice", last_name="Smith")
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        self.campaign = EmailCampaign.objects.create(
            subject="Hi", body="<p>Hello</p>", audience_type="subscribers", member_email_scope="primary", status="draft"
        )

    def email(self, provider, max_send_rate):
        return EmailServiceConfig.objects.create(
            is_active=True, provider=provider, from_email="noreply@example.com", max_send_rate=max_send_rate
        )

    def test_ses_is_paced_at_the_operators_cap(self, _client, _send, slot):
        self.email("ses", 4)

        send_campaign(self.campaign, self.sender)

        self.assertEqual(slot.call_count, 2)
        self.assertEqual({call.args for call in slot.call_args_list}, {("ses", 4.0)})

    def test_an_uncapped_ses_campaign_is_not_paced(self, _client, _send, slot):
        self.email("ses", 0)

        send_campaign(self.campaign, self.sender)

        self.assertEqual({call.args for call in slot.call_args_list}, {("ses", 0.0)})

    def use_graph(self, max_send_rate):
        create_graph_config(
            scope=GRAPH_TEST_SCOPE,
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret="not-a-real-secret",
            messages_per_minute=12,
        )
        self.email("graph", max_send_rate)

    def test_graph_is_paced_at_its_ceiling_when_the_cap_is_higher(self, _client, _send, slot):
        self.use_graph(max_send_rate=10)

        send_campaign(self.campaign, self.sender)

        provider, rate = slot.call_args.args
        self.assertEqual(provider, "graph")
        self.assertAlmostEqual(rate, 0.2)

    def test_graph_is_never_unpaced_even_when_the_cap_is_off(self, _client, _send, slot):
        self.use_graph(max_send_rate=0)

        send_campaign(self.campaign, self.sender)

        provider, rate = slot.call_args.args
        self.assertEqual(provider, "graph")
        self.assertAlmostEqual(rate, 0.2)

    def test_every_recipient_takes_a_slot_from_the_shared_schedule(self, _client, _send, slot):
        make_member(email="bob@example.com", first_name="Bob", last_name="Jones")
        self.email("ses", 4)

        send_campaign(self.campaign, self.sender)

        self.assertEqual(slot.call_count, 3)
