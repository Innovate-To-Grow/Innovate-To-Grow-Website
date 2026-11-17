"""Preparing an unsent, one-address retry after a campaign recipient bounced."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_superuser
from apps.mail.models import BouncedAddress, EmailCampaign, RecipientLog

from .test_duplicate import make_campaign


class RetryDuplicateViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def duplicate_url(self, campaign):
        return reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[campaign.pk])

    def test_bounced_recipient_can_prepare_a_single_address_retry_draft(self):
        campaign = make_campaign()
        RecipientLog.objects.create(
            campaign=campaign, email_address="one@example.com", status="bounced", sent_at=timezone.now()
        )
        BouncedAddress.objects.create(address="one@example.com", soft_count=1)
        url = self.duplicate_url(campaign) + "?retry_address=one%40example.com"

        page = self.client.get(url)
        self.assertContains(page, "Retry only one@example.com")
        response = self.client.post(
            self.duplicate_url(campaign),
            {"name": "Retry", "audience": "retry", "retry_address": "one@example.com"},
        )

        copy = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertRedirects(response, reverse("admin:mail_emailcampaign_change", args=[copy.pk]))
        self.assertEqual((copy.status, copy.audience_type, copy.manual_emails), ("draft", "manual", "one@example.com"))
        self.assertFalse(copy.recipient_logs.exists())

    def test_retry_draft_refuses_an_unrelated_or_permanently_bounced_address(self):
        campaign = make_campaign()
        RecipientLog.objects.create(
            campaign=campaign, email_address="one@example.com", status="bounced", sent_at=timezone.now()
        )
        BouncedAddress.objects.create(address="one@example.com", hard_count=1, category_counts={"hard": 1})

        for address in ("other@example.com", "one@example.com"):
            response = self.client.post(
                self.duplicate_url(campaign),
                {"audience": "retry", "retry_address": address},
            )
            self.assertEqual(response.status_code, 400)
        BouncedAddress.objects.filter(address="one@example.com").update(
            hard_count=0, category_counts={"mailbox_disabled": 1}
        )
        self.assertEqual(
            self.client.post(
                self.duplicate_url(campaign), {"audience": "retry", "retry_address": "one@example.com"}
            ).status_code,
            400,
        )
        self.assertEqual(EmailCampaign.objects.count(), 1)

    def test_retry_draft_requires_the_original_message_to_have_been_sent(self):
        campaign = make_campaign()
        RecipientLog.objects.create(campaign=campaign, email_address="one@example.com", status="pending")
        BouncedAddress.objects.create(address="one@example.com", soft_count=1)

        response = self.client.post(
            self.duplicate_url(campaign), {"audience": "retry", "retry_address": "one@example.com"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailCampaign.objects.count(), 1)
