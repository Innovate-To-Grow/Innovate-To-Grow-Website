"""Concurrent retry POSTs remain idempotent."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep

from django.core.cache import cache
from django.db import OperationalError, close_old_connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, EmailCampaign, RecipientLog
from apps.mail.services.campaign.content.retry_delivery import retry_delivery_snapshot_token

from .test_duplicate import make_campaign


class RetryDuplicateConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        cache.clear()
        admin = make_superuser()
        self.clients = [Client(), Client()]
        for client in self.clients:
            client.force_login(admin)
        self.config = EmailServiceConfig.objects.create(
            name="Reviewed SES", is_active=True, provider="ses", from_email="retry@example.org"
        )
        self.address = "concurrent@example.com"
        member = make_member(email=self.address)
        self.campaign = make_campaign()
        RecipientLog.objects.create(
            campaign=self.campaign,
            member=member,
            email_address=self.address,
            status="bounced",
            sent_at=timezone.now(),
        )
        row = BouncedAddress.objects.create(address=self.address, soft_count=1, category_counts={"transient": 1})
        BouncedAddressCampaign.objects.create(
            bounced_address=row,
            campaign_id=self.campaign.pk,
            source=BouncedAddressCampaign.Source.GRAPH,
            match=BouncedAddressCampaign.Match.EXACT,
            bounce_count=1,
            graph_category_counts={"transient": 1},
            first_at=timezone.now(),
            last_at=timezone.now(),
        )

    def test_concurrent_posts_create_only_one_sendable_retry(self):
        barrier = Barrier(2)
        url = reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[self.campaign.pk])
        data = {
            "name": "Concurrent retry",
            "audience": "retry",
            "retry_address": self.address,
            "retry_delivery_snapshot": retry_delivery_snapshot_token(self.config),
        }

        def post(client):
            close_old_connections()
            barrier.wait()
            for attempt in range(5):
                try:
                    response = client.post(url, data)
                    close_old_connections()
                    return response.status_code
                except OperationalError:
                    # SQLite locks the whole test DB; PostgreSQL waits on the source row. Retry only that test lock.
                    close_old_connections()
                    if attempt == 4:
                        raise
                    sleep(0.02)
            raise AssertionError("unreachable")

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(post, self.clients))

        self.assertEqual(statuses, [302, 302])
        retries = EmailCampaign.objects.filter(retry_source_campaign=self.campaign, retry_address=self.address)
        self.assertEqual(retries.count(), 1)
        self.assertEqual(retries.get().status, "draft")
