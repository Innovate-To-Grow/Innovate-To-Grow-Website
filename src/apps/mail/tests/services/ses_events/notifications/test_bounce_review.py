from django.test import TestCase
from django.utils import timezone

from apps.event.tests.helpers import make_member
from apps.mail.models import BouncedAddress, EmailCampaign, RecipientLog
from apps.mail.services.audience.suppression import is_suppressed
from apps.mail.services.campaign.content.retry import retry_address_for
from apps.mail.services.email_monitoring.ses_events.notification import handle_notification
from apps.mail.tests.services.bounced_addresses.helpers import count_now

from .envelopes import _envelope

Suggestion = BouncedAddress.Suggestion


class SesBounceReviewTests(TestCase):
    def test_ses_notifications_drive_review_hold_and_retry(self):
        cases = (
            ("Transient", "MailboxFull", "", True, False, ""),
            ("Transient", "General", "451 4.4.1 Connection timed out", True, False, ""),
            ("Transient", "General", "Out of the office until Monday", False, False, ""),
            ("Transient", "General", "554 delivery error", False, False, Suggestion.VERIFY_EVIDENCE),
            ("Transient", "AttachmentRejected", "", False, False, Suggestion.FIX_CONTENT),
            ("Transient", "ContentRejected", "", False, False, Suggestion.FIX_CONTENT),
            ("Permanent", "UnsubscribedRecipient", "", False, True, Suggestion.SES_HOLD),
            ("Permanent", "OnAccountSuppressionList", "", False, True, Suggestion.SES_HOLD),
            ("Permanent", "General", "550 5.1.1 no such user", False, True, Suggestion.UNDELIVERABLE),
        )
        for i, (kind, subtype, diagnostic, retry, held, suggestion) in enumerate(cases):
            with self.subTest(subtype=subtype, diagnostic=diagnostic):
                email = f"contact{i}@example.org"
                member = make_member(email=email)
                campaign = EmailCampaign.objects.create(subject="Sent", body="Body", status="sent")
                RecipientLog.objects.create(
                    campaign=campaign,
                    member=member,
                    email_address=email,
                    status="sent",
                    sent_at=timezone.now(),
                    provider="ses",
                    provider_message_id=str(i),
                )
                bounce = {
                    "bounceType": kind,
                    "bounceSubType": subtype,
                    "bouncedRecipients": [{"emailAddress": email, "diagnosticCode": diagnostic}],
                }
                handle_notification(_envelope("Bounce", {"mail": {"messageId": str(i)}, "bounce": bounce}))
                self.assertEqual(is_suppressed(email), held)
                count_now()
                self.assertEqual(BouncedAddress.objects.get(address=email).suggestion, suggestion)
                self.assertEqual(bool(retry_address_for(campaign, email)), retry)
