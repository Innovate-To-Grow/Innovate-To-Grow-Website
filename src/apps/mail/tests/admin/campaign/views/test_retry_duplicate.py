"""Retry drafts retain their immutable identity, audience and sending snapshot."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.mail.models import EmailCampaign

from .retry_duplicate_helpers import RetryDuplicateViewTestCase
from .test_duplicate import make_campaign


class RetryDuplicateViewTests(RetryDuplicateViewTestCase):
    def test_retry_page_and_draft_are_locked_to_one_eligible_address_and_method_snapshot(self):
        campaign, member, _contact = self.evidence()
        url = self.duplicate_url(campaign) + "?retry_address=one%40example.com"

        page = self.client.get(url)
        self.assertContains(page, "Retry only one@example.com")
        self.assertContains(page, "AWS SES")
        self.assertNotContains(page, "Same audience")
        self.assertNotContains(page, "New, empty Manual Emails list")
        response = self.post_retry(campaign, token=page.context["retry_delivery_snapshot"])

        copy = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertRedirects(response, reverse("admin:mail_emailcampaign_change", args=[copy.pk]))
        self.assertEqual((copy.status, copy.audience_type, copy.manual_emails), ("draft", "manual", "one@example.com"))
        self.assertEqual((copy.retry_source_campaign_id, copy.retry_address), (campaign.pk, "one@example.com"))
        self.assertEqual(
            (copy.retry_email_config_id, copy.retry_sending_provider, copy.retry_from_email),
            (self.config.pk, "ses", "retry-a@example.org"),
        )
        self.assertFalse(copy.recipient_logs.exists())
        self.assertEqual(member.pk, ContactEmail.objects.get(email_address="one@example.com").member_id)

    def test_retry_identity_normalizes_case_before_uniqueness(self):
        campaign, _member, _contact = self.evidence()
        self.assertEqual(self.post_retry(campaign, "ONE@EXAMPLE.COM").status_code, 302)
        self.assertEqual(self.post_retry(campaign, "one@example.com", token="").status_code, 302)

        retry = EmailCampaign.objects.get(retry_source_campaign=campaign)
        self.assertEqual((retry.retry_address, retry.manual_emails), ("one@example.com", "one@example.com"))
        self.assertEqual(EmailCampaign.objects.filter(retry_source_campaign=campaign).count(), 1)

    def test_repeated_post_reuses_original_snapshot_even_after_global_method_changes(self):
        campaign, _member, _contact = self.evidence()
        first = self.post_retry(campaign)
        retry = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertEqual(first.status_code, 302)

        self.config.provider = "smtp"
        self.config.from_email = "retry-b@example.org"
        self.config.save(update_fields=["provider", "from_email", "updated_at"])
        page = self.client.get(self.duplicate_url(campaign) + "?retry_address=one%40example.com")
        self.assertContains(page, "This one-address retry draft already exists")
        self.assertContains(page, "AWS SES")
        self.assertContains(page, "retry-a@example.org")
        second = self.post_retry(campaign, token="")

        self.assertEqual(second.status_code, 302)
        self.assertEqual(EmailCampaign.objects.filter(retry_source_campaign=campaign).count(), 1)
        retry.refresh_from_db()
        self.assertEqual((retry.retry_sending_provider, retry.retry_from_email), ("ses", "retry-a@example.org"))

    def test_creation_rejects_a_sending_method_change_after_get(self):
        campaign, _member, _contact = self.evidence()
        page = self.client.get(self.duplicate_url(campaign) + "?retry_address=one%40example.com")
        reviewed = page.context["retry_delivery_snapshot"]
        self.config.provider = "smtp"
        self.config.from_email = "changed@example.org"
        self.config.save(update_fields=["provider", "from_email", "updated_at"])

        response = self.post_retry(campaign, token=reviewed)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "sending method changed", status_code=400)
        self.assertFalse(EmailCampaign.objects.filter(retry_source_campaign=campaign).exists())

    def test_retry_shape_and_member_relations_cannot_be_edited_into_bulk(self):
        campaign, member, _contact = self.evidence()
        self.post_retry(campaign)
        retry = EmailCampaign.objects.get(retry_source_campaign=campaign)

        retry.manual_emails = "one@example.com\ntwo@example.com"
        with self.assertRaises(ValidationError):
            retry.save()
        retry.refresh_from_db()
        retry.audience_type = "all_members"
        with self.assertRaises(ValidationError):
            retry.save()
        retry.refresh_from_db()
        with transaction.atomic(), self.assertRaises(ValidationError):
            retry.selected_members.add(member)

        retry.retry_source_campaign = None
        with self.assertRaises(ValidationError):
            retry.save()
        retry.refresh_from_db()
        retry.retry_address = "other@example.com"
        retry.manual_emails = "other@example.com"
        with self.assertRaises(ValidationError):
            retry.save()
        retry.refresh_from_db()
        retry.retry_sending_provider = "smtp"
        retry.retry_from_email = "other-sender@example.org"
        with self.assertRaises(ValidationError):
            retry.save()

    def test_retry_provenance_cannot_be_added_to_an_existing_campaign_or_point_to_itself(self):
        source, _member, _contact = self.evidence()
        ordinary = make_campaign(name="Existing ordinary campaign")
        ordinary.audience_type = "manual"
        ordinary.manual_emails = "one@example.com"
        ordinary.retry_source_campaign = source
        ordinary.retry_address = "one@example.com"
        ordinary.retry_email_config = self.config
        ordinary.retry_sending_provider = self.config.provider
        ordinary.retry_from_email = self.config.from_email
        with self.assertRaises(ValidationError):
            ordinary.save()

        self_retry = EmailCampaign(
            subject="Self retry",
            audience_type="manual",
            manual_emails="one@example.com",
            retry_address="one@example.com",
            retry_email_config=self.config,
            retry_sending_provider=self.config.provider,
            retry_from_email=self.config.from_email,
        )
        self_retry.retry_source_campaign_id = self_retry.pk
        with self.assertRaises(ValidationError):
            self_retry.save()

    def test_a_new_retry_must_start_as_a_draft(self):
        source, _member, _contact = self.evidence()
        retry = EmailCampaign(
            subject="Already sent retry",
            status="sent",
            audience_type="manual",
            manual_emails="one@example.com",
            retry_source_campaign=source,
            retry_address="one@example.com",
            retry_email_config=self.config,
            retry_sending_provider=self.config.provider,
            retry_from_email=self.config.from_email,
        )
        with self.assertRaises(ValidationError):
            retry.save()

    def test_database_constraint_keeps_the_retry_address_locked(self):
        campaign, _member, _contact = self.evidence()
        self.post_retry(campaign)
        retry = EmailCampaign.objects.get(retry_source_campaign=campaign)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmailCampaign.objects.filter(pk=retry.pk).update(manual_emails="one@example.com\ntwo@example.com")

        retry.refresh_from_db()
        self.assertEqual((retry.audience_type, retry.manual_emails), ("manual", "one@example.com"))
