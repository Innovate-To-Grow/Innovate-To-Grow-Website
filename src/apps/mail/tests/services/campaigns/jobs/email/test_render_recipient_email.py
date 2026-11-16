from unittest.mock import patch

from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch.email_job import _render_recipient_email
from apps.mail.services.send_campaign.recipients import RecipientContext

from ..durable_queue_helpers import DurableCampaignQueueTestCase


class RenderRecipientEmailTests(DurableCampaignQueueTestCase):
    def test_a_message_that_carries_the_login_link_keeps_no_sent_items_copy(self):
        campaign, log = self._queued_email()
        EmailCampaign.objects.filter(pk=campaign.pk).update(body='<p><a href="{{login_link}}">Sign in</a></p>')
        log = RecipientLog.objects.select_related("campaign", "member").get(pk=log.pk)
        context = "apps.mail.services.campaign.dispatch.email_job._recipient_context"
        token_link = "https://i2g.example/login-link#token=abc"
        for values, issued, keep in (
            ({"login_link": token_link}, token_link, False),
            # The sign-in page that stands in when no link was issued is no credential.
            ({"login_link": "https://i2g.example/login"}, "", True),
        ):
            with (
                self.subTest(issued=issued),
                patch(context, return_value=RecipientContext(values, issued_login_link=issued)),
            ):
                *_rendered, keep_sent_copy = _render_recipient_email(log)

                self.assertIs(keep_sent_copy, keep)
