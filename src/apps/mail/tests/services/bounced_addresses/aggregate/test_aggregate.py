"""Counting bounce reports and SES events per address: once each, kept after purges, never touching members."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.models import EmailBounce
from apps.core.services.email.telemetry.retention import purge_expired
from apps.core.tests.services.email_monitoring.helpers import make_email, monitoring_settings
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressCampaign
from apps.mail.services.email_monitoring.addresses import aggregate

from ..helpers import add_email, count_now, make_bounce, make_campaign, make_person, make_ses_log, settled

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
            match_method="message_id",
            trusted_recipient=True,
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

    def test_reports_matched_to_the_sites_mail_are_counted_apart(self):
        for match in ("message_id", "recipient", "unmatched"):
            make_bounce(recipient="m@example.org", match_method=match)

        count_now()

        row = BouncedAddress.objects.get(address="m@example.org")
        self.assertEqual((row.hard_count, row.matched_count), (3, 2))
        self.assertTrue(row.has_matched_evidence)

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
        make_bounce(
            recipient="m@example.org",
            email=email,
            campaign_id=blast.pk,
            match_method="message_id",
            trusted_recipient=True,
        )
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
