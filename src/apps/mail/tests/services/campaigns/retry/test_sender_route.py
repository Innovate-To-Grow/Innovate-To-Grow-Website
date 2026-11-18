"""A send-side rejection must use a different, verifiable sending service, even when other evidence is temporary."""

from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.mail.models import BouncedAddressCampaign, EmailCampaign
from apps.mail.services.campaign.content.retry import RetryRefused, assert_retry_campaign_eligible
from apps.mail.tests.admin.campaign.views.retry_duplicate_helpers import RetryDuplicateViewTestCase


class SenderRouteTests(RetryDuplicateViewTestCase):
    def source(self, category, provider):
        campaign, *_ = self.evidence(category=category)
        log = campaign.recipient_logs.get()
        log.provider = provider
        log.save(update_fields=["provider"])
        return campaign, log

    def test_same_provider_with_different_from_address_is_refused(self):
        source, _ = self.source("relay_denied", "ses")
        self.config.from_email = "another-sender@example.org"
        self.config.save(update_fields=["from_email"])

        page = self.client.get(self.duplicate_url(source), {"retry_address": "one@example.com"})
        self.assertContains(page, "different configured sending provider")
        self.assertNotContains(page, 'id="duplicate-campaign-form"')
        reply = self.post_retry(source)

        self.assertContains(reply, "different configured sending provider", status_code=400)
        self.assertFalse(EmailCampaign.objects.filter(retry_source_campaign=source).exists())

    def test_known_alternate_provider_is_accepted_and_pinned(self):
        source, _ = self.source("spam_rejected", "graph")

        page = self.client.get(self.duplicate_url(source), {"retry_address": "one@example.com"})
        self.assertEqual(page.context["original_provider"], "Microsoft Graph")
        self.assertEqual(page.context["retry_sending_method"], "AWS SES")
        self.assertContains(page, 'id="duplicate-campaign-form"')
        self.assertEqual(self.post_retry(source).status_code, 302)
        retry = EmailCampaign.objects.get(retry_source_campaign=source)
        self.assertEqual(retry.retry_sending_provider, "ses")
        self.assertEqual(assert_retry_campaign_eligible(retry).rejected_sender_provider, "graph")

    def test_only_a_matching_accepted_outbound_record_can_resolve_an_unknown_route(self):
        source, log = self.source("relay_denied", "")
        fields = {
            "campaign_id": source.pk,
            "source_type": "mail.recipientlog",
            "source_id": str(log.pk),
            "recipient": log.email_address,
        }
        make_email(**{**fields, "recipient": "other@example.org"}, provider="graph")
        make_email(**fields, status="failed", provider="smtp")
        self.assertContains(self.post_retry(source), "cannot be verified", status_code=400)

        make_email(**fields, provider="graph")
        self.assertEqual(self.post_retry(source).status_code, 302)

    def test_conflicting_original_sender_records_require_review(self):
        source, log = self.source("spam_rejected", "smtp")
        make_email(
            campaign_id=source.pk,
            source_type="mail.recipientlog",
            source_id=str(log.pk),
            recipient=log.email_address,
            provider="graph",
        )

        self.assertContains(self.post_retry(source), "cannot be verified", status_code=400)

    def test_new_sender_refusal_before_dispatch_overrides_older_temporary_evidence(self):
        source, _ = self.source("mailbox_full", "ses")
        self.assertEqual(self.post_retry(source).status_code, 302)
        retry = EmailCampaign.objects.get(retry_source_campaign=source)
        self.assertIsNone(assert_retry_campaign_eligible(retry).rejected_sender_provider)

        BouncedAddressCampaign.objects.filter(campaign_id=source.pk).update(
            graph_category_counts={"mailbox_full": 1, "relay_denied": 1}
        )

        with self.assertRaisesMessage(RetryRefused, "different configured sending provider"):
            assert_retry_campaign_eligible(retry)
