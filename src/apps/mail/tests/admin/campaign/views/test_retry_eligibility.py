"""Retry offers accept only live contacts and exact allowlisted evidence."""

from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.services.email_monitoring.helpers import make_bounce
from apps.event.tests.helpers import make_member
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, EmailCampaign, RecipientLog
from apps.mail.services.campaign.content.duplicate import duplicate_campaign
from apps.mail.services.campaign.content.retry import RetryRefused

from .retry_duplicate_helpers import RetryDuplicateViewTestCase
from .test_duplicate import make_campaign


class RetryEligibilityViewTests(RetryDuplicateViewTestCase):
    def test_only_explicit_retryable_categories_from_this_exact_campaign_are_allowed(self):
        for index, category in enumerate(("transient", "mailbox_full", "spam_rejected", "relay_denied")):
            with self.subTest(category=category):
                address = f"allowed-{index}@example.com"
                campaign, _member, _contact = self.evidence(address, category=category)
                self.assertEqual(self.post_retry(campaign, address).status_code, 302)

        for index, category in enumerate(("delayed", "unknown", "policy_rejected", "hard", "mailbox_disabled")):
            with self.subTest(category=category):
                address = f"blocked-{index}@example.com"
                campaign, _member, _contact = self.evidence(address, category=category)
                self.assertEqual(self.post_retry(campaign, address).status_code, 400)

        campaign, _member, _contact = self.evidence("wrong-campaign@example.com")
        other = make_campaign(name="Other")
        RecipientLog.objects.create(
            campaign=other,
            email_address="wrong-campaign@example.com",
            status="bounced",
            sent_at=timezone.now(),
        )
        self.assertEqual(self.post_retry(other, "wrong-campaign@example.com").status_code, 400)

    def test_likely_or_mixed_likely_evidence_never_confers_retry_eligibility(self):
        campaign, _member, _contact = self.evidence("likely@example.com")
        link = BouncedAddressCampaign.objects.get(campaign_id=campaign.pk)
        link.match = BouncedAddressCampaign.Match.LIKELY
        link.save(update_fields=["match"])
        self.assertEqual(self.post_retry(campaign, "likely@example.com").status_code, 400)

        # An aggregate label may later become exact, but prior likely counts are deliberately not exact evidence.
        link.match = BouncedAddressCampaign.Match.EXACT
        link.graph_category_counts = {}
        link.save(update_fields=["match", "graph_category_counts"])
        self.assertEqual(self.post_retry(campaign, "likely@example.com").status_code, 400)

    def test_suppression_complaint_and_ses_permanent_evidence_block_direct_post(self):
        for field in ("suppressed_at", "complaint_count", "ses_permanent_count"):
            with self.subTest(field=field):
                address = f"{field}@example.com"
                campaign, _member, _contact = self.evidence(address)
                row = BouncedAddress.objects.get(address=address)
                setattr(row, field, timezone.now() if field == "suppressed_at" else 1)
                row.save(update_fields=[field])
                self.assertEqual(self.post_retry(campaign, address).status_code, 400)

    def test_unaggregated_provider_permanent_and_complaint_events_block_direct_post(self):
        for event in ("complaint", "permanent"):
            with self.subTest(event=event):
                address = f"raw-{event}@example.com"
                campaign, _member, _contact = self.evidence(address)
                log = RecipientLog.objects.get(campaign=campaign, email_address=address)
                values = (
                    {"complained_at": timezone.now()}
                    if event == "complaint"
                    else {"bounced_at": timezone.now(), "bounce_type": "Permanent"}
                )
                RecipientLog.objects.filter(pk=log.pk).update(**values)
                self.assertEqual(self.post_retry(campaign, address).status_code, 400)

        address = "raw-graph-hard@example.com"
        campaign, _member, _contact = self.evidence(address)
        make_bounce(
            recipient=address,
            classification="hard",
            category="hard",
            campaign_id=campaign.pk,
            match_method="message_id",
        )
        self.assertEqual(self.post_retry(campaign, address).status_code, 400)

    def test_exact_ses_transient_is_allowed_but_other_ses_types_are_not(self):
        for index, bounce_type in enumerate(("Transient", "Undetermined", "Permanent")):
            with self.subTest(bounce_type=bounce_type):
                address = f"ses-{index}@example.com"
                campaign = make_campaign()
                member = make_member(email=address)
                RecipientLog.objects.create(
                    campaign=campaign,
                    member=member,
                    email_address=address,
                    status="bounced",
                    sent_at=timezone.now(),
                )
                row = BouncedAddress.objects.create(
                    address=address,
                    ses_transient_count=1 if bounce_type == "Transient" else 0,
                    ses_undetermined_count=1 if bounce_type == "Undetermined" else 0,
                    ses_permanent_count=1 if bounce_type == "Permanent" else 0,
                )
                BouncedAddressCampaign.objects.create(
                    bounced_address=row,
                    campaign_id=campaign.pk,
                    source=BouncedAddressCampaign.Source.SES,
                    match=BouncedAddressCampaign.Match.EXACT,
                    bounce_count=1,
                    first_at=timezone.now(),
                    last_at=timezone.now(),
                    ses_bounce_type=bounce_type,
                    ses_bounced_at=timezone.now(),
                )
                expected = 302 if bounce_type == "Transient" else 400
                self.assertEqual(self.post_retry(campaign, address).status_code, expected)

    def test_unsubscribed_unverified_or_inactive_contact_is_rechecked_on_get_and_post(self):
        for field in ("subscribe", "verified", "is_active"):
            with self.subTest(field=field):
                address = f"{field}@example.com"
                campaign, member, contact = self.evidence(address)
                if field == "is_active":
                    member.is_active = False
                    member.save(update_fields=["is_active"])
                else:
                    setattr(contact, field, False)
                    contact.save(update_fields=[field])
                page = self.client.get(self.duplicate_url(campaign) + f"?retry_address={address}")
                self.assertNotContains(page, f"Retry only {address}")
                self.assertEqual(self.post_retry(campaign, address).status_code, 400)

    def test_unlinked_or_ambiguous_contact_is_rejected_on_get_and_post(self):
        unlinked, _member, _contact = self.evidence("unlinked@example.com", contact=False)
        self.assertNotContains(
            self.client.get(self.duplicate_url(unlinked) + "?retry_address=unlinked%40example.com"),
            "Retry only unlinked@example.com",
        )
        self.assertEqual(self.post_retry(unlinked, "unlinked@example.com").status_code, 400)

        ambiguous, _member, _contact = self.evidence("ambiguous@example.com")
        second = make_member(email="AMBIGUOUS@example.com")
        self.assertIsNotNone(second.pk)
        self.assertNotContains(
            self.client.get(self.duplicate_url(ambiguous) + "?retry_address=ambiguous%40example.com"),
            "Retry only ambiguous@example.com",
        )
        self.assertEqual(self.post_retry(ambiguous, "ambiguous@example.com").status_code, 400)

    def test_send_confirmation_get_rechecks_live_eligibility(self):
        campaign, _member, contact = self.evidence()
        self.post_retry(campaign)
        retry = EmailCampaign.objects.get(retry_source_campaign=campaign)
        contact.subscribe = False
        contact.save(update_fields=["subscribe"])

        response = self.client.get(reverse("admin:mail_emailcampaign_send_confirm", args=[retry.pk]))

        self.assertRedirects(response, reverse("admin:mail_emailcampaign_change", args=[retry.pk]))
        retry.refresh_from_db()
        self.assertEqual(retry.status, "draft")
        self.assertFalse(retry.recipient_logs.exists())

    def test_retry_draft_cannot_be_laundered_through_generic_duplication(self):
        source, _member, _contact = self.evidence()
        self.post_retry(source)
        retry = EmailCampaign.objects.get(retry_source_campaign=source)
        with self.assertRaises(RetryRefused):
            duplicate_campaign(retry)

        url = self.duplicate_url(retry)
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.post(url, {"audience": "same"}).status_code, 400)
        change = self.client.get(reverse("admin:mail_emailcampaign_change", args=[retry.pk]))
        self.assertNotContains(change, url)

        response = self.client.post(
            reverse("admin:mail_emailcampaign_changelist"),
            {"action": "duplicate_campaigns_action", "_selected_action": [str(retry.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailCampaign.objects.count(), 2)
        self.assertTrue(any("cannot be duplicated" in str(message) for message in get_messages(response.wsgi_request)))
