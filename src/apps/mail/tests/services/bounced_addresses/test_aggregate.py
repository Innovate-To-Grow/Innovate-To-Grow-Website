"""Counting bounce reports and SES events per address: once each, kept after purges, never touching members."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.models import EmailBounce
from apps.core.services.email.telemetry.retention import purge_expired
from apps.core.tests.services.email_monitoring.helpers import make_email, monitoring_settings
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, BouncedAddressCampaign
from apps.mail.services.email_monitoring.addresses import aggregate

from .helpers import add_email, count_now, make_bounce, make_campaign, make_person, make_ses_log, settled

Status = BouncedAddress.Status
Match = BouncedAddressCampaign.Match


class GraphCountingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_each_report_counts_once_by_classification_and_address_case(self):
        make_bounce(recipient="Pat@Example.org", classification="hard", status_code="5.1.1")
        make_bounce(recipient="pat@example.org", classification="soft", status_code="5.2.2")
        make_bounce(recipient="pat@example.org", classification="rejected", status_code="5.7.1")
        make_bounce(recipient="pat@example.org", classification="delayed", status_code="4.4.7")
        make_bounce(recipient="pat@example.org", classification="unknown", status_code="")

        result = count_now()
        again = count_now()

        row = BouncedAddress.objects.get(address="pat@example.org")
        counts = (row.hard_count, row.soft_count, row.rejected_count, row.delayed_count, row.unknown_count)
        self.assertEqual(counts, (1, 1, 1, 1, 1))
        self.assertEqual(result["graph"], 5)
        self.assertEqual(again["graph"], 0)
        self.assertEqual(BouncedAddress.objects.count(), 1)

    def test_the_latest_report_gives_the_last_reason_and_dates_span_all_reports(self):
        now = timezone.now()
        make_bounce(
            recipient="a@example.org", received_at=now - timedelta(days=3), status_code="5.2.2", classification="soft"
        )
        make_bounce(
            recipient="a@example.org",
            received_at=now,
            status_code="5.1.1",
            reason="Recipient mailbox does not exist",
            diagnostic_code="smtp; 550 5.1.1 Bearer abcdefghijklmnop " + "x" * 70,
            remote_mta="mx.example.org",
        )

        count_now()

        row = BouncedAddress.objects.get(address="a@example.org")
        self.assertEqual(row.last_status_code, "5.1.1")
        self.assertEqual(row.last_remote_mta, "mx.example.org")
        self.assertIn("[redacted]", row.last_diagnostic)
        self.assertNotIn("x" * 70, row.last_diagnostic)
        self.assertEqual(row.first_bounce_at, now - timedelta(days=3))
        self.assertEqual(row.last_bounce_at, now)
        self.assertEqual(row.suggestion, BouncedAddress.Suggestion.UNDELIVERABLE)

    def test_reports_naming_no_recipient_are_not_counted(self):
        make_bounce(recipient="")

        count_now()

        self.assertFalse(BouncedAddress.objects.exists())
        self.assertEqual(BounceAggregationState.objects.get(source="graph").processed_total, 1)

    def test_counts_survive_the_bounce_retention_purge(self):
        old = timezone.now() - timedelta(days=400)
        make_bounce(recipient="kept@example.org", received_at=old)
        count_now()

        purged = purge_expired()
        make_bounce(recipient="kept@example.org")
        count_now()

        self.assertEqual(purged["bounces"], 1)
        self.assertEqual(EmailBounce.objects.count(), 1)
        self.assertEqual(BouncedAddress.objects.get(address="kept@example.org").hard_count, 2)

    def test_reports_still_settling_wait_for_a_later_run(self):
        make_bounce(recipient="late@example.org")

        with monitoring_settings(address_settle_seconds=3600):
            first = aggregate.run()
        second = count_now()

        self.assertEqual(first["graph"], 0)
        self.assertEqual(second["graph"], 1)
        self.assertEqual(aggregate.pending(), 0)

    def test_a_page_load_counts_at_most_its_share(self):
        for index in range(5):
            make_bounce(recipient=f"p{index}@example.org")

        with settled(), monitoring_settings(address_settle_seconds=0, address_batch_size=2):
            result = aggregate.run(max_rows=3, wait=False)

        self.assertEqual(result["graph"], 3)
        self.assertEqual(aggregate.pending(), 2)

    def test_matched_campaigns_are_exact_and_unmatched_ones_likely_only_when_unique(self):
        blast = make_campaign("Blast")
        other = make_campaign("Other")
        email = make_email(recipient="m@example.org", campaign_id=blast.pk)
        make_bounce(recipient="m@example.org", email=email, campaign_id=blast.pk)
        # An unmatched report: one campaign mailed the address in the window before it.
        make_ses_log(blast, "u@example.org", bounced=False, status="sent")
        make_bounce(recipient="u@example.org")
        # Two campaigns mailed this one: no attribution rather than a guess.
        make_ses_log(blast, "two@example.org", bounced=False, status="sent")
        make_ses_log(other, "two@example.org", bounced=False, status="sent")
        make_bounce(recipient="two@example.org")

        count_now()

        exact = BouncedAddressCampaign.objects.get(bounced_address__address="m@example.org")
        likely = BouncedAddressCampaign.objects.get(bounced_address__address="u@example.org")
        self.assertEqual((exact.campaign_id, exact.match), (blast.pk, Match.EXACT))
        self.assertEqual((likely.campaign_id, likely.match), (blast.pk, Match.LIKELY))
        self.assertFalse(BouncedAddressCampaign.objects.filter(bounced_address__address="two@example.org").exists())

    def test_counting_never_changes_members_contacts_or_subscriptions(self):
        member = make_person("member@example.org")
        add_email(member, "second@example.org", subscribe=True)
        before = list(ContactEmail.objects.order_by("pk").values())
        make_bounce(recipient="member@example.org", classification="hard")
        make_bounce(recipient="second@example.org", classification="hard")
        campaign = make_campaign()
        make_ses_log(campaign, "member@example.org", complained=True, bounced=False)

        count_now()
        aggregate.refresh_all()

        member.refresh_from_db()
        self.assertTrue(member.is_active)
        self.assertEqual(list(ContactEmail.objects.order_by("pk").values()), before)
        self.assertFalse(BouncedAddress.objects.filter(suppressed_at__isnull=False).exists())
        row = BouncedAddress.objects.get(address="member@example.org")
        self.assertEqual((row.role, row.member_id), (BouncedAddress.Role.PRIMARY, member.pk))


class ReopenTests(TestCase):
    def setUp(self):
        cache.clear()
        make_bounce(recipient="d@example.org", classification="soft", status_code="5.2.2")
        count_now()
        self.dismissed_at = timezone.now() - timedelta(minutes=1)
        BouncedAddress.objects.filter(address="d@example.org").update(
            status=Status.DISMISSED, resolution="dismiss", reviewed_at=self.dismissed_at
        )

    def test_a_new_hard_or_rejected_bounce_reopens_a_dismissed_address(self):
        for classification in ("hard", "rejected"):
            with self.subTest(classification=classification):
                BouncedAddress.objects.filter(address="d@example.org").update(status=Status.DISMISSED)
                make_bounce(recipient="d@example.org", classification=classification, status_code="5.1.1")

                count_now()

                row = BouncedAddress.objects.get(address="d@example.org")
                self.assertEqual(row.status, Status.OPEN)
                entry = BouncedAddressAction.objects.filter(address="d@example.org").latest("created_at")
                self.assertEqual(entry.action, BouncedAddressAction.Action.REOPEN)
                self.assertIsNone(entry.actor)

    def test_a_report_received_before_the_dismissal_does_not_reopen_it(self):
        make_bounce(recipient="d@example.org", received_at=self.dismissed_at - timedelta(hours=1))

        count_now()

        row = BouncedAddress.objects.get(address="d@example.org")
        self.assertEqual((row.status, row.hard_count), (Status.DISMISSED, 1))

    def test_soft_bounces_and_delays_leave_it_dismissed(self):
        make_bounce(recipient="d@example.org", classification="soft", status_code="4.2.2")
        make_bounce(recipient="d@example.org", classification="delayed", status_code="4.4.7")

        count_now()

        self.assertEqual(BouncedAddress.objects.get(address="d@example.org").status, Status.DISMISSED)

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


class RebuildAndRefreshTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rebuild_recounts_stored_records_and_keeps_review_and_suppression(self):
        make_bounce(recipient="r@example.org")
        make_bounce(recipient="r@example.org", classification="soft", status_code="5.2.2")
        count_now()
        stamp = timezone.now()
        BouncedAddress.objects.filter(address="r@example.org").update(
            status=Status.DISMISSED, reviewed_at=stamp, suppressed_at=stamp, suppression="suppressed", hard_count=99
        )

        aggregate.rebuild()
        count_now()

        row = BouncedAddress.objects.get(address="r@example.org")
        self.assertEqual((row.hard_count, row.soft_count), (1, 1))
        self.assertEqual(row.status, Status.DISMISSED)
        self.assertEqual(row.suppressed_at, stamp)

    def test_refresh_all_follows_contact_changes_made_elsewhere(self):
        make_bounce(recipient="moved@example.org")
        count_now()
        self.assertEqual(BouncedAddress.objects.get(address="moved@example.org").role, BouncedAddress.Role.NONE)
        member = make_person("moved@example.org")

        changed = aggregate.refresh_all()

        row = BouncedAddress.objects.get(address="moved@example.org")
        self.assertEqual(changed, 1)
        self.assertEqual((row.role, row.member_id), (BouncedAddress.Role.PRIMARY, member.pk))

    def test_a_stop_request_ends_the_runs(self):
        make_bounce(recipient="s@example.org")

        with settled():
            result = aggregate.run(should_stop=lambda: True)

        self.assertEqual(result["graph"], 0)
        self.assertEqual(aggregate.refresh_all(should_stop=lambda: True), 0)
