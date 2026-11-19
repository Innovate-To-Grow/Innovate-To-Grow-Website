"""Shared fixtures for retry-draft admin view tests."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, RecipientLog
from apps.mail.services.campaign.content.retry_delivery import retry_delivery_snapshot_token

from .test_duplicate import make_campaign


class RetryDuplicateViewTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        self.config = EmailServiceConfig.objects.create(
            name="Reviewed SES", is_active=True, provider="ses", from_email="retry-a@example.org", from_name="I2G"
        )

    def duplicate_url(self, campaign):
        return reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[campaign.pk])

    def evidence(self, address="one@example.com", *, category="transient", campaign=None, contact=True):
        campaign = campaign or make_campaign()
        member = make_member(email=address) if contact else None
        RecipientLog.objects.create(
            campaign=campaign,
            member=member,
            email_address=address,
            status="bounced",
            provider="graph",
            sent_at=timezone.now(),
        )
        graph_counts = {category: 1}
        row = BouncedAddress.objects.create(
            address=address.lower(),
            soft_count=1 if category in {"transient", "mailbox_full"} else 0,
            rejected_count=1 if category in {"spam_rejected", "relay_denied", "policy_rejected"} else 0,
            hard_count=1 if category in {"hard", "mailbox_disabled"} else 0,
            delayed_count=1 if category == "delayed" else 0,
            unknown_count=1 if category == "unknown" else 0,
            category_counts=graph_counts,
        )
        BouncedAddressCampaign.objects.create(
            bounced_address=row,
            campaign_id=campaign.pk,
            source=BouncedAddressCampaign.Source.GRAPH,
            match=BouncedAddressCampaign.Match.EXACT,
            bounce_count=1,
            graph_category_counts=graph_counts,
            first_at=timezone.now(),
            last_at=timezone.now(),
        )
        contact_row = (
            ContactEmail.objects.filter(member=member, email_address__iexact=address).first() if member else None
        )
        return campaign, member, contact_row

    def post_retry(self, campaign, address="one@example.com", *, token=None, name="Retry"):
        return self.client.post(
            self.duplicate_url(campaign),
            {
                "name": name,
                "audience": "retry",
                "retry_address": address,
                "retry_delivery_snapshot": token if token is not None else retry_delivery_snapshot_token(self.config),
            },
        )
