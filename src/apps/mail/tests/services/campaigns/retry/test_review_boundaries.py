"""A stale staff review cannot widen the audience or send to a reassigned address."""

from apps.authn.models import ContactEmail, Member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.content.retry import RetryRefused, assert_retry_campaign_eligible
from apps.mail.services.campaign.dispatch.queueing import queue_email_campaign
from apps.mail.tests.admin.campaign.views.retry_duplicate_helpers import RetryDuplicateViewTestCase


class RetryReviewBoundariesTests(RetryDuplicateViewTestCase):
    def test_stale_link_cannot_fall_back_to_original_audience(self):
        source, _, contact = self.evidence()
        url = self.duplicate_url(source) + "?retry_address=one%40example.com"
        self.assertContains(self.client.get(url), "Retry only one@example.com")
        contact.subscribe = False
        contact.save(update_fields=["subscribe"])
        response = self.client.get(url)
        self.assertNotContains(response, "Same audience", status_code=400)
        for audience in ("same", "manual", "invalid", None):
            data = {"audience": audience} if audience is not None else {}
            self.assertEqual(self.client.post(url, data).status_code, 400)
        self.assertEqual(self.post_retry(source).status_code, 400)
        self.assertEqual(EmailCampaign.objects.count(), 1)

    def test_changed_or_partial_review_fields_do_not_create_an_ordinary_campaign(self):
        source, _, _ = self.evidence()
        url = self.duplicate_url(source)
        for data in ({"retry_address": "one@example.com"}, {"audience": "same", "retry_delivery_snapshot": "stale"}):
            self.assertEqual(self.client.post(url, data).status_code, 400)
        response = self.client.post(
            url + "?retry_address=two%40example.com", {"audience": "retry", "retry_address": "one@example.com"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailCampaign.objects.count(), 1)

    def test_source_owner_is_required_before_and_after_draft_creation(self):
        source, old, contact = self.evidence()
        self.assertEqual(self.post_retry(source).status_code, 302)
        retry = EmailCampaign.objects.get(retry_source_campaign=source)
        new = Member.objects.create_user(password="fixture-password")
        ContactEmail.objects.filter(pk=contact.pk).update(member=new)
        self.assertEqual(RecipientLog.objects.get(campaign=source).member_id, old.pk)
        self.assertEqual(self.post_retry(source).status_code, 400)
        with self.assertRaises(RetryRefused):
            queue_email_campaign(retry, sent_by=new)
        self.assertFalse(retry.recipient_logs.exists())
        RecipientLog.objects.filter(campaign=source).update(member=None)
        self.assertEqual(self.post_retry(source).status_code, 400)

    def test_source_state_and_late_delivery_are_rechecked_on_cached_campaign(self):
        source, _, _ = self.evidence()
        self.assertEqual(self.post_retry(source).status_code, 302)
        retry = EmailCampaign.objects.select_related("retry_source_campaign").get(retry_source_campaign=source)
        self.assertIsNotNone(assert_retry_campaign_eligible(retry))
        for state in ("draft", "queued", "sending"):
            EmailCampaign.objects.filter(pk=source.pk).update(status=state)
            with self.assertRaises(RetryRefused):
                assert_retry_campaign_eligible(retry)
        EmailCampaign.objects.filter(pk=source.pk).update(status="partial")
        self.assertIsNotNone(assert_retry_campaign_eligible(retry))
        RecipientLog.objects.filter(campaign=source).update(status="delivered")
        with self.assertRaises(RetryRefused):
            assert_retry_campaign_eligible(retry)

    def test_draft_with_previous_recipient_log_cannot_be_queued(self):
        source, member, _ = self.evidence()
        self.assertEqual(self.post_retry(source).status_code, 302)
        retry = EmailCampaign.objects.get(retry_source_campaign=source)
        log = RecipientLog.objects.create(
            campaign=retry, member=member, email_address=retry.retry_address, status="sent"
        )
        with self.assertRaises(RetryRefused):
            queue_email_campaign(retry, sent_by=member)
        log.refresh_from_db()
        self.assertEqual(log.status, "sent")
