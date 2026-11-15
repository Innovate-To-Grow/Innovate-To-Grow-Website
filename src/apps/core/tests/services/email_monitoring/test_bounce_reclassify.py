"""Saving a report's category and SMTP code (``bounces.store``), classifying stored reports again after the rules
change, classifying the reports the previous release saved without a category, and each email's worst bounce."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, OutboundEmail
from apps.core.services.email.bounces.dsn import parse_report
from apps.core.services.email.bounces.store import (
    classify_unclassified,
    reclassify_stored,
    refresh_worst,
    save_report,
)

from .helpers import make_bounce, make_email
from .review_cases import CASES_BY_NAME

Category = EmailBounce.Category
TIMEOUT_EXPIRED = "550 5.4.316 Message expired, connection refused(Socket error code 10061)"


class SaveCategoryTests(TestCase):
    def save(self, raw):
        report = parse_report(raw)
        return save_report(mailbox="i2g@ucmerced.edu", graph_id="AAMkAD-c", received_at=timezone.now(), report=report)

    def test_a_report_is_saved_with_its_category_and_reply_code(self):
        email = make_email(internet_message_id="<review-1@ucmerced.edu>", recipient="refused@example.org")

        (bounce,) = self.save(CASES_BY_NAME["connection_refused_expired"].raw).created

        self.assertEqual(
            (bounce.category, bounce.classification, bounce.is_permanent, bounce.smtp_code, bounce.reason),
            (Category.TRANSIENT, "soft", False, "550", "Delivery expired: connection refused"),
        )
        self.assertEqual(bounce.email, email)
        email.refresh_from_db()
        self.assertEqual((email.delivery_status, email.bounce_classification), ("failure_confirmed", "soft"))

    def test_the_verdict_comes_from_the_stored_scrubbed_diagnostic(self):
        token = "A" * 80
        raw = CASES_BY_NAME["business_connection_timeout"].raw.replace(
            b"Connection timed out", f"{token} Connection timed out".encode()
        )

        (bounce,) = self.save(raw).created

        self.assertNotIn(token, bounce.diagnostic_code)
        self.assertIn("[redacted] Connection timed out", bounce.diagnostic_code)
        self.assertEqual((bounce.category, bounce.reason), (Category.TRANSIENT, "Connection timed out"))


class ReclassifyTests(TestCase):
    def test_stored_reports_are_classified_again_with_the_current_rules(self):
        email = make_email(delivery_status="failure_confirmed", bounce_classification="hard")
        before = timezone.now() - timedelta(minutes=5)
        old = make_bounce(
            email=email,
            classification="hard",
            category="",
            is_permanent=True,
            status_code="5.4.316",
            diagnostic_code=TIMEOUT_EXPIRED,
        )
        same = make_bounce(status_code="5.1.1", diagnostic_code="550 5.1.1 user unknown", is_permanent=True)
        EmailBounce.objects.filter(pk=same.pk).update(reason="Recipient mailbox does not exist", smtp_code="550")
        EmailBounce.objects.filter(pk__in=[old.pk, same.pk]).update(updated_at=before)

        changed = reclassify_stored(batch_size=1)

        old.refresh_from_db()
        same.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertEqual(
            (old.category, old.classification, old.is_permanent, old.smtp_code),
            (Category.TRANSIENT, "soft", False, "550"),
        )
        self.assertGreater(old.updated_at, before)
        self.assertEqual(same.updated_at, before)
        email.refresh_from_db()
        self.assertEqual(email.bounce_classification, "soft")
        self.assertEqual(reclassify_stored(), 0)

    def test_every_report_saved_without_a_category_is_classified_batch_by_batch(self):
        rows = [
            make_bounce(category="", status_code="5.0.0", diagnostic_code="550 5.0.0 user unknown") for _ in range(3)
        ]
        delay = make_bounce(category="", action="delayed", classification="delayed", status_code="4.4.7")
        nothing = make_bounce(category="", classification="hard", status_code="", diagnostic_code="")

        self.assertEqual(classify_unclassified(batch_size=2), 5)
        self.assertEqual(classify_unclassified(), 0)

        for row in rows:
            row.refresh_from_db()
            self.assertEqual((row.category, row.classification), (Category.HARD, "hard"))
        delay.refresh_from_db()
        nothing.refresh_from_db()
        self.assertEqual(delay.category, Category.DELAYED)
        self.assertEqual((nothing.category, nothing.classification, nothing.is_permanent), ("unknown", "unknown", None))

    def test_a_stored_report_that_reads_as_delivered_is_kept_as_unknown(self):
        odd = make_bounce(category="", action="delivered", status_code="2.0.0", classification="hard")

        self.assertEqual(classify_unclassified(), 1)

        odd.refresh_from_db()
        self.assertEqual(
            (odd.category, odd.classification, odd.reason), ("unknown", "unknown", "The report gives no status code")
        )

    def test_an_emails_worst_bounce_ignores_delays_and_reports_of_other_emails(self):
        email = make_email(delivery_status="failure_confirmed", bounce_classification="hard")
        quiet = make_email(delivery_status="delayed", bounce_classification="")
        make_bounce(email=email, classification="soft", category=Category.TRANSIENT)
        make_bounce(email=email, classification="rejected", category=Category.SPAM_REJECTED)
        make_bounce(email=email, classification="delayed", category=Category.DELAYED)
        make_bounce(email=quiet, classification="delayed", category=Category.DELAYED)

        refresh_worst({email.pk, quiet.pk})

        email.refresh_from_db()
        quiet.refresh_from_db()
        self.assertEqual(email.bounce_classification, "rejected")
        self.assertEqual(quiet.bounce_classification, "")
        self.assertEqual(OutboundEmail.objects.get(pk=quiet.pk).delivery_status, "delayed")
