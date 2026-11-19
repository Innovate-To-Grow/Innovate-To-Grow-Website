"""Submitted one-address retries retain their source/address identity even if staff try to delete their logs."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.urls import reverse

from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.tests.admin.campaign.views.retry_duplicate_helpers import RetryDuplicateViewTestCase


class RetryHistoryTests(RetryDuplicateViewTestCase):
    def create_retry(self):
        source, member, _ = self.evidence()
        self.assertEqual(self.post_retry(source).status_code, 302)
        return source, EmailCampaign.objects.get(retry_source_campaign=source), member

    def test_never_queued_draft_can_be_deleted_and_recreated(self):
        source, retry, _ = self.create_retry()
        first_pk = retry.pk
        retry.delete()
        self.assertEqual(self.post_retry(source).status_code, 302)
        second = EmailCampaign.objects.get(retry_source_campaign=source)
        self.assertNotEqual(second.pk, first_pk)

    def test_stale_draft_cannot_overwrite_submission_or_delete_it(self):
        _, retry, member = self.create_retry()
        stale = EmailCampaign.objects.get(pk=retry.pk)
        queue_email_campaign(retry, sent_by=member)
        with self.assertRaisesMessage(ValidationError, "cannot return to draft"):
            stale.save()
        with self.assertRaises(ProtectedError), transaction.atomic():
            stale.delete()
        retry.refresh_from_db()
        self.assertEqual(retry.status, "queued")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_admin_and_bulk_delete_preserve_every_submitted_outcome(self):
        source, retry, member = self.create_retry()
        queue_email_campaign(retry, sent_by=member)
        log = retry.recipient_logs.get()
        for campaign_status, log_status in (("queued", "pending"), ("failed", "uncertain"), ("sent", "sent")):
            with self.subTest(campaign=campaign_status, log=log_status):
                EmailCampaign.objects.filter(pk=retry.pk).update(status=campaign_status)
                RecipientLog.objects.filter(pk=log.pk).update(status=log_status)
                for obj, url, model in (
                    (log, "admin:mail_recipientlog_delete", RecipientLog),
                    (retry, "admin:mail_emailcampaign_delete", EmailCampaign),
                ):
                    response = self.client.post(reverse(url, args=[obj.pk]), {"post": "yes"})
                    self.assertEqual(response.status_code, 403)
                    with self.assertRaises(ProtectedError), transaction.atomic():
                        model.objects.filter(pk=obj.pk).delete()
                bulk = self.client.post(
                    reverse("admin:mail_emailcampaign_changelist"),
                    {"action": "delete_selected", "_selected_action": [str(retry.pk)], "post": "yes"},
                )
                self.assertEqual(bulk.status_code, 403)
                self.assertEqual(self.post_retry(source).status_code, 302)
                self.assertEqual(EmailCampaign.objects.get(retry_source_campaign=source).pk, retry.pk)
                self.assertEqual(retry.recipient_logs.count(), 1)

    def test_submission_without_logs_cannot_be_reset_or_deleted(self):
        _, retry, _ = self.create_retry()
        retry.status = "sending"
        retry.save(update_fields=["status"])
        retry.status = "failed"
        retry.save(update_fields=["status"])
        self.assertFalse(retry.recipient_logs.exists())
        retry.status = "draft"
        with self.assertRaisesMessage(ValidationError, "cannot return to draft"):
            retry.save(update_fields=["status"])
        with self.assertRaises(ProtectedError), transaction.atomic():
            retry.delete()

    def test_log_preserves_draft_with_partial_dispatch_state(self):
        _, retry, member = self.create_retry()
        log = RecipientLog.objects.create(campaign=retry, member=member, email_address=retry.retry_address)
        with self.assertRaises(ProtectedError), transaction.atomic():
            log.delete()
        with self.assertRaises(ProtectedError), transaction.atomic():
            retry.delete()

    def test_ordinary_campaign_with_recipient_history_remains_deletable(self):
        source, _, _ = self.evidence()
        source.delete()
        self.assertFalse(RecipientLog.objects.exists())
