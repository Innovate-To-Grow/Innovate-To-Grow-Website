from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.mail.models import BouncedAddress, BouncedAddressAction, BouncedAddressCampaign
from apps.mail.tests.services.bounced_addresses.aggregate.test_aggregate import Status

from ..helpers import count_now, make_bounce, make_campaign, make_ses_log


class ReopenTests(TestCase):
    def setUp(self):
        cache.clear()
        make_bounce(recipient="d@example.org", classification="soft", status_code="5.2.2")
        count_now()
        self.dismissed_at = timezone.now() - timedelta(minutes=1)
        BouncedAddress.objects.filter(address="d@example.org").update(
            status=Status.DISMISSED, resolution="dismiss", reviewed_at=self.dismissed_at
        )

    def test_a_new_matched_missing_address_or_disabled_mailbox_reopens_a_dismissed_address(self):
        for category, status_code, match in (
            ("hard", "5.1.1", "message_id"),
            ("mailbox_disabled", "5.2.1", "recipient"),
        ):
            with self.subTest(category=category):
                BouncedAddress.objects.filter(address="d@example.org").update(status=Status.DISMISSED)
                make_bounce(recipient="d@example.org", category=category, status_code=status_code, match_method=match)

                count_now()

                row = BouncedAddress.objects.get(address="d@example.org")
                self.assertEqual(row.status, Status.OPEN)
                entry = BouncedAddressAction.objects.filter(address="d@example.org").latest("created_at")
                self.assertEqual(entry.action, BouncedAddressAction.Action.REOPEN)
                self.assertIsNone(entry.actor)

    def test_an_unmatched_report_never_reopens_it(self):
        # Anyone can mail the mailbox a report-shaped message: it is counted, but changes no queue state.
        make_bounce(recipient="d@example.org", classification="hard", status_code="5.1.1", match_method="unmatched")

        count_now()

        row = BouncedAddress.objects.get(address="d@example.org")
        self.assertEqual((row.status, row.hard_count, row.matched_count), (Status.DISMISSED, 1, 0))
        self.assertFalse(row.has_matched_evidence)

    def test_a_report_received_before_the_dismissal_does_not_reopen_it(self):
        make_bounce(
            recipient="d@example.org", received_at=self.dismissed_at - timedelta(hours=1), match_method="message_id"
        )

        count_now()

        row = BouncedAddress.objects.get(address="d@example.org")
        self.assertEqual((row.status, row.hard_count), (Status.DISMISSED, 1))

    def test_soft_bounces_and_delays_leave_it_dismissed(self):
        make_bounce(recipient="d@example.org", classification="soft", status_code="4.2.2")
        make_bounce(recipient="d@example.org", classification="delayed", status_code="4.4.7")

        count_now()

        self.assertEqual(BouncedAddress.objects.get(address="d@example.org").status, Status.DISMISSED)

    def test_matched_rejections_temporary_failures_and_unknowns_leave_it_dismissed(self):
        # Only strong evidence against the address reopens it; a rejection points at our sending or their policy.
        for category, classification in (
            ("spam_rejected", "rejected"),
            ("relay_denied", "rejected"),
            ("policy_rejected", "rejected"),
            ("transient", "soft"),
            ("mailbox_full", "soft"),
            ("unknown", "unknown"),
        ):
            make_bounce(
                recipient="d@example.org", category=category, classification=classification, match_method="message_id"
            )

        count_now()

        row = BouncedAddress.objects.get(address="d@example.org")
        self.assertEqual((row.status, row.matched_count), (Status.DISMISSED, 6))
        self.assertFalse(row.actions.filter(action=BouncedAddressAction.Action.REOPEN).exists())

    def test_a_new_ses_permanent_bounce_or_complaint_reopens_it(self):
        campaign = make_campaign()
        make_ses_log(campaign, "d@example.org", bounce_type="Transient")
        count_now()
        self.assertEqual(BouncedAddress.objects.get(address="d@example.org").status, Status.DISMISSED)

        make_ses_log(make_campaign("Second"), "d@example.org", bounce_type="Permanent")
        count_now()
        self.assertEqual(BouncedAddress.objects.get(address="d@example.org").status, Status.OPEN)

        BouncedAddress.objects.filter(address="d@example.org").update(status=Status.DISMISSED)
        make_ses_log(make_campaign("Third"), "d@example.org", complained=True, bounced=False)
        count_now()
        self.assertEqual(BouncedAddress.objects.get(address="d@example.org").status, Status.OPEN)


class SesCountingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_ses_bounces_and_complaints_are_counted_once_per_recipient_log(self):
        first, second, third, fourth = (make_campaign(f"C{index}") for index in range(4))
        log = make_ses_log(first, "Ses@Example.org", bounce_type="Permanent")
        make_ses_log(second, "ses@example.org", bounce_type="Transient")
        make_ses_log(third, "ses@example.org", bounce_type="Undetermined")
        make_ses_log(fourth, "ses@example.org", complained=True, bounced=False)

        count_now()
        # The log is saved again by a later, unrelated event: counted again, it must not add anything.
        log.last_event_type = "Open"
        log.save()
        count_now()

        row = BouncedAddress.objects.get(address="ses@example.org")
        counts = (row.ses_permanent_count, row.ses_transient_count, row.ses_undetermined_count, row.complaint_count)
        self.assertEqual(counts, (1, 1, 1, 1))
        self.assertEqual(row.hard_total, 1)
        self.assertEqual(row.suggestion, BouncedAddress.Suggestion.UNSUBSCRIBE)
        self.assertEqual(row.ses_last["event"], "complaint")
        self.assertEqual(BouncedAddressCampaign.objects.filter(bounced_address=row, source="ses").count(), 4)

    def test_ses_counts_stay_when_the_campaign_is_deleted(self):
        campaign = make_campaign()
        make_ses_log(campaign, "gone@example.org")
        count_now()

        campaign.delete()
        count_now()

        self.assertEqual(BouncedAddress.objects.get(address="gone@example.org").ses_permanent_count, 1)
