"""The new delivery statuses as staff see them: a chip with its own icon on the email log, a meaning that says what
it does not prove on the email page, and the campaign page's evidence tile and failed-recipient list."""

import re

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OutboundEmail
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign

DeliveryStatus = OutboundEmail.DeliveryStatus
CHIP = r'<span class="i2g-monitor-chip i2g-monitor-chip--{value}">\s*<span[^>]*>(\w+)</span>{label}'
ICONS = {
    DeliveryStatus.NO_BOUNCE: "task_alt",
    DeliveryStatus.DELIVERED: "mark_email_read",
    DeliveryStatus.QUARANTINED: "gpp_maybe",
    DeliveryStatus.FILTERED_AS_SPAM: "report",
}


class _PageCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())


class EmailLogChipTests(_PageCase):
    def test_each_new_status_has_its_own_chip_icon_and_label(self):
        for value in ICONS:
            make_email(recipient=f"{value}@example.com", delivery_status=value)

        html = self.client.get(reverse("admin:mail_email_monitoring_emails")).content.decode()

        for value, icon in ICONS.items():
            with self.subTest(value=value):
                found = re.search(CHIP.format(value=value, label=re.escape(str(DeliveryStatus(value).label))), html)
                self.assertIsNotNone(found)
                self.assertEqual(found.group(1), icon)

    def test_no_bounce_is_explained_as_likely_and_not_proof(self):
        email = make_email(delivery_status=DeliveryStatus.NO_BOUNCE)

        page = self.client.get(reverse("admin:mail_email_monitoring_email", args=[email.pk]))

        self.assertContains(page, "No bounce received")
        self.assertContains(page, "it was likely delivered, but this is not proof")
        self.assertContains(page, "<dt>Message trace</dt><dd>not checked</dd>", html=False)

    def test_a_quarantined_email_shows_its_trace_verdict_and_meaning(self):
        email = make_email(
            delivery_status=DeliveryStatus.QUARANTINED, trace_status="quarantined", trace_checked_at=timezone.now()
        )

        page = self.client.get(reverse("admin:mail_email_monitoring_email", args=[email.pk]))

        self.assertContains(page, "<code>quarantined</code> · checked")
        self.assertContains(page, "it waits for review and was not delivered")


class CampaignPageTests(_PageCase):
    def setUp(self):
        super().setUp()
        self.campaign = EmailCampaign.objects.create(
            subject="News", body="<p>x</p>", status="sent", total_recipients=5, sent_at=timezone.now()
        )
        self.url = reverse("admin:mail_email_monitoring_campaign", args=[self.campaign.pk])

    def email(self, recipient, delivery_status, trace_status=""):
        return make_email(
            campaign_id=self.campaign.pk,
            recipient=recipient,
            delivery_status=delivery_status,
            trace_status=trace_status,
            trace_checked_at=timezone.now() if trace_status else None,
        )

    def test_the_evidence_tile_counts_each_kind_apart(self):
        self.email("a@example.com", DeliveryStatus.DELIVERED, "delivered")
        self.email("b@example.com", DeliveryStatus.DELIVERED, "expanded")
        self.email("c@example.com", DeliveryStatus.NO_BOUNCE)
        self.email("d@example.com", DeliveryStatus.QUARANTINED, "quarantined")
        self.email("e@example.com", DeliveryStatus.FILTERED_AS_SPAM, "filteredAsSpam")

        html = " ".join(self.client.get(self.url).content.decode().split())

        self.assertIn(
            "<p>Delivery evidence</p><strong>2</strong><small>delivered (message trace) · 1 no bounce received "
            "(not proof) · 2 quarantined or spam</small>",
            html,
        )

    def test_quarantined_and_spam_recipients_are_listed_with_the_trace_verdict(self):
        self.email("clean@example.com", DeliveryStatus.DELIVERED, "delivered")
        self.email("likely@example.com", DeliveryStatus.NO_BOUNCE)
        self.email("held@example.com", DeliveryStatus.QUARANTINED, "quarantined")
        self.email("junk@example.com", DeliveryStatus.FILTERED_AS_SPAM, "filteredAsSpam")

        response = self.client.get(self.url)

        self.assertEqual(response.context["monitoring"]["failed_total"], 2)
        failed = {email.recipient for email in response.context["monitoring"]["failed"]}
        self.assertEqual(failed, {"held@example.com", "junk@example.com"})
        self.assertContains(response, "Message trace: <code>quarantined</code>")
        self.assertContains(response, "Message trace: <code>filteredAsSpam</code>")

    def test_a_campaign_with_only_clean_results_says_it_proves_no_delivery(self):
        self.email("clean@example.com", DeliveryStatus.DELIVERED, "delivered")
        self.email("likely@example.com", DeliveryStatus.NO_BOUNCE)

        response = self.client.get(self.url)

        self.assertEqual(response.context["monitoring"]["failed_total"], 0)
        self.assertContains(response, "which does not prove delivery")
