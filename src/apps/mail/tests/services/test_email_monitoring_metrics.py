"""The dashboard's calculations: scope parsing, headline figures by level, chart series, campaign comparisons and
monitoring, the email log's filters, and the bounce processor's health levels."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import EmailCategory, EmailMonitorState
from apps.core.services.email.bounces import ensure_scheduled
from apps.core.tests.services.email_monitoring.helpers import make_attempt, make_bounce, make_email, monitoring_settings
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.email_monitoring import campaigns, charts, health, log, overview, scope


class ScopeTests(SimpleTestCase):
    NOW = timezone.make_aware(datetime(2026, 11, 9, 15, 30))

    def test_presets(self):
        current = scope.parse_scope({"range": "24h", "provider": "graph"}, now=self.NOW)

        self.assertEqual(
            (current.start, current.end, current.bucket), (self.NOW - timedelta(hours=24), self.NOW, "hour")
        )
        self.assertEqual(current.params(), {"range": "24h", "provider": "graph"})
        self.assertEqual(scope.parse_scope({"range": "30d"}, now=self.NOW).bucket, "day")

    def test_a_custom_range_covers_whole_local_days(self):
        current = scope.parse_scope({"range": "custom", "start": "2026-11-01", "end": "2026-11-03"}, now=self.NOW)

        self.assertEqual(current.start, timezone.make_aware(datetime(2026, 11, 1)))
        self.assertEqual(current.end, timezone.make_aware(datetime(2026, 11, 4)))
        self.assertEqual(current.params(), {"range": "custom", "start": "2026-11-01", "end": "2026-11-03"})

    def test_invalid_input_falls_back_to_the_default_with_a_reason(self):
        for params, reason in (
            ({"range": "custom", "start": "2026-11-05", "end": "2026-11-01"}, "ends before it starts"),
            ({"range": "custom", "start": "2024-01-01", "end": "2026-11-01"}, "at most"),
            ({"range": "custom", "start": "nonsense", "end": ""}, "Enter a start"),
            ({"range": "custom", "start": "2026-02-30", "end": "2026-03-01"}, "real calendar dates"),
            ({"range": "custom", "start": "9999-12-30", "end": "9999-12-31"}, "within the years"),
        ):
            with self.subTest(params=params):
                current = scope.parse_scope(params, now=self.NOW)
                self.assertEqual(current.key, scope.DEFAULT_RANGE)
                self.assertIn(reason, current.errors[0])
        self.assertEqual(scope.parse_scope({"range": "1y", "provider": "evil"}, now=self.NOW).params(), {"range": "7d"})


class OverviewTests(TestCase):
    def test_message_recipient_and_attempt_figures_stay_apart(self):
        accepted = make_email(recipient_count=3, recipients=["a@x", "b@x", "c@x"], attempt_count=2)
        make_attempt(accepted, 1, outcome="transient", http_status=429, error_kind="throttled", response_ms=100)
        make_attempt(accepted, 2, response_ms=300)
        failed = make_email(status="failed")
        make_attempt(failed, outcome="permanent", http_status=400, error_kind="bad_request", response_ms=200)
        make_email(status="uncertain")
        make_email(status="not_sent", attempt_count=0)
        bounced = make_email(delivery_status="failure_confirmed", bounce_classification="hard")
        make_bounce(email=bounced, recipient="person@example.com")
        make_bounce(email=bounced, recipient="person@example.com", classification="soft", received_at=timezone.now())
        make_bounce(email=bounced, recipient="person@example.com", classification="delayed")
        make_bounce(recipient="stranger@example.com", match_method="unmatched")
        make_email(category=EmailCategory.ACCESS_CHECK)

        figures = overview.overview(scope.parse_scope({}))

        messages, attempts, bounces = figures["messages"], figures["attempts"], figures["bounces"]
        self.assertEqual((messages["total"], messages["accepted"], messages["failed"]), (5, 2, 1))
        self.assertEqual((messages["uncertain"], messages["not_sent"], messages["submitted"]), (1, 1, 4))
        self.assertEqual(messages["api_success_rate"], 50.0)
        self.assertEqual((messages["bounced"], messages["bounce_rate"], messages["retried"]), (1, 50.0, 1))
        self.assertEqual((messages["recipients"], messages["accepted_recipients"]), (7, 4))
        self.assertEqual((attempts["total"], attempts["retries"], attempts["throttled"]), (3, 1, 1))
        self.assertEqual((attempts["avg_response_ms"], attempts["success_rate"]), (200, 33.3))
        # Two failure reports for one recipient still count one bounced recipient.
        self.assertEqual((bounces["total"], bounces["unmatched"], bounces["bounced_recipients"]), (4, 1, 1))
        self.assertEqual(bounces["recipient_bounce_rate"], 25.0)
        self.assertEqual(figures["latest_error"]["http_status"], 400)

    def test_an_empty_range_has_no_rates(self):
        figures = overview.overview(scope.parse_scope({}))

        self.assertIsNone(figures["messages"]["api_success_rate"])
        self.assertIsNone(figures["latest_error"])

    def test_the_provider_filter_scopes_every_figure(self):
        make_email(provider="graph")
        make_email(provider="ses")

        self.assertEqual(overview.overview(scope.parse_scope({"provider": "ses"}))["messages"]["total"], 1)


class ChartTests(TestCase):
    def test_daily_series_fill_every_bucket_and_the_table_lists_the_busy_ones(self):
        make_attempt(make_email(), outcome="accepted")
        make_attempt(make_email(status="failed"), outcome="permanent", http_status=403, error_kind="forbidden")
        make_bounce(classification="soft")

        data = charts.charts(scope.parse_scope({"range": "7d"}))

        self.assertEqual(data["bucket"], "day")
        self.assertIn(len(data["volume"]["labels"]), (7, 8))
        self.assertEqual(sum(data["volume"]["series"]["emails"]), 2)
        self.assertEqual(sum(data["api"]["series"]["accepted"]), 1)
        self.assertEqual(sum(data["bounces"]["series"]["soft"]), 1)
        self.assertEqual(data["volume"]["table"][-1]["values"], [2])
        self.assertEqual(data["http_errors"], [{"label": "HTTP 403", "count": 1, "share": 100.0}])
        self.assertEqual([row["key"] for row in data["categories"]], ["campaign"])

    def test_failure_reasons_include_emails_stopped_before_any_attempt(self):
        make_attempt(
            make_email(status="failed"), outcome="permanent", http_status=400, error_kind="bad_request", error_code="E1"
        )
        make_email(status="not_sent", attempt_count=0, last_error_kind="config", last_error="No configuration.")

        reasons = charts.failure_reasons(scope.parse_scope({}))

        self.assertEqual(
            {row["kind"] for row in reasons}, {"Rejected request (HTTP 4xx)", "Configuration or mailbox scope"}
        )

    def test_bounce_reasons_leave_delays_out(self):
        make_bounce(classification="hard", reason="Recipient not found", status_code="5.1.10")
        make_bounce(classification="delayed", status_code="4.4.7")

        self.assertEqual([row["status_code"] for row in charts.bounce_reasons(scope.parse_scope({}))], ["5.1.10"])


class CampaignTests(TestCase):
    def test_comparisons_count_each_campaign(self):
        first = EmailCampaign.objects.create(name="First", subject="A", body="<p>x</p>", status="sent")
        make_email(campaign_id=first.pk, attempt_count=3)
        make_email(campaign_id=first.pk, status="failed")
        make_email(campaign_id=first.pk, delivery_status="failure_confirmed")

        (row,) = campaigns.comparisons(scope.parse_scope({}))

        self.assertEqual(
            (row["name"], row["emails"], row["accepted"], row["failed"], row["bounced"]), ("First", 3, 2, 1, 1)
        )
        self.assertEqual((row["retries"], row["bounce_rate"]), (2, 50.0))

    def test_campaign_monitoring_counts_errors_bounces_and_lists_failures(self):
        campaign = EmailCampaign.objects.create(
            name="C", subject="S", body="<p>x</p>", status="sent", total_recipients=3
        )
        ok = make_email(campaign_id=campaign.pk)
        make_attempt(ok)
        failed = make_email(campaign_id=campaign.pk, recipient="bad@example.com", status="failed")
        make_attempt(failed, outcome="permanent", http_status=400, error_kind="bad_request")
        make_bounce(campaign_id=campaign.pk, email=ok, classification="hard")
        RecipientLog.objects.create(campaign=campaign, email_address="person@example.com", status="sent")
        RecipientLog.objects.create(campaign=campaign, email_address="bad@example.com", status="failed")

        monitoring = campaigns.campaign_monitoring(campaign)

        self.assertEqual(monitoring["failed_total"], 1)
        self.assertEqual([row["kind"] for row in monitoring["error_kinds"]], ["bad_request"])
        self.assertEqual({row["key"]: row["count"] for row in monitoring["bounce_classes"]}["hard"], 1)
        self.assertEqual(monitoring["recipient_log"], {"sent": 1, "failed": 1})
        self.assertEqual(monitoring["coverage"], "full")
        self.assertEqual(sum(monitoring["timeline"]["series"]["accepted"]), 1)
        self.assertEqual(sum(monitoring["timeline"]["series"]["bounced"]), 1)
        # A campaign sent within minutes is charted by the minute, not as one hourly point.
        self.assertEqual(monitoring["timeline"]["bucket"], "minute")


class LogTests(TestCase):
    def rows(self, **params):
        listing = log.email_listing(params)
        return list(log.email_rows(scope.parse_scope(params), listing))

    def test_filters_combine_and_unknown_values_are_ignored(self):
        campaign_id = "1f2e3d4c-1111-4222-8333-444455556666"
        a = make_email(recipient="alpha@example.com", category=EmailCategory.SIGN_IN)
        b = make_email(
            recipient="beta@example.com",
            status="failed",
            last_error_kind="throttled",
            attempt_count=2,
            campaign_id=campaign_id,
        )

        self.assertEqual(self.rows(category="sign_in"), [a])
        self.assertEqual(self.rows(status="failed", error="throttled", retried="1"), [b])
        self.assertEqual(self.rows(campaign=campaign_id), [b])
        self.assertEqual(self.rows(q="ALPHA"), [a])
        self.assertEqual(self.rows(q=str(b.correlation_id)), [b])
        self.assertEqual(len(self.rows(status="'; DROP TABLE", sort="password", page_size="9999")), 2)

    def test_sorting_and_pagination(self):
        for name in ("c", "a", "b"):
            make_email(recipient=f"{name}@example.com")
        listing = log.email_listing({"sort": "recipient", "dir": "asc", "page_size": "25"})

        page = log.paginate(log.email_rows(scope.parse_scope({}), listing), listing)

        self.assertEqual(
            [row.recipient for row in page.object_list], ["a@example.com", "b@example.com", "c@example.com"]
        )
        self.assertEqual((listing.page_size, page.paginator.num_pages), (25, 1))

    def test_bounce_filters(self):
        hard = make_bounce(classification="hard", match_method="message_id", recipient="x@example.com")
        make_bounce(classification="soft", match_method="unmatched")
        listing = log.bounce_listing({"classification": "hard", "match": "message_id", "q": "x@ex"})

        self.assertEqual(list(log.bounce_rows(scope.parse_scope({}), listing)), [hard])


class HealthTests(TestCase):
    def level(self, **values):
        now = timezone.now()
        defaults = {"last_run_finished_at": now, "paused": False, "consecutive_failures": 0, "last_success_at": now}
        return health._level(SimpleNamespace(**{**defaults, **values}), active=True, now=now)

    def test_levels(self):
        self.assertEqual(health._level(None, active=True, now=timezone.now()), "waiting")
        self.assertEqual(self.level(paused=True), "paused")
        self.assertEqual(self.level(consecutive_failures=2), "error")
        self.assertEqual(self.level(last_success_at=timezone.now() - timedelta(hours=5)), "warning")
        self.assertEqual(self.level(), "ok")
        self.assertEqual(health._level(None, active=False, now=timezone.now()), "inactive")

    @monitoring_settings(bounce_processing_enabled=False)
    def test_switched_off_is_inactive(self):
        self.assertEqual(self.level(), "inactive")

    def test_the_summary_reads_the_state_the_next_scan_and_when_monitoring_began(self):
        email = make_email()
        now = timezone.now()
        EmailMonitorState.objects.create(
            mailbox="i2g@ucmerced.edu", last_run_finished_at=now, last_success_at=now, last_run_stats={"listed": 3}
        )
        ensure_scheduled()

        with patch.object(health, "active_reader", return_value=(object(), "i2g@ucmerced.edu", "")):
            summary = health.monitoring_health()

        bounces = summary["bounces"]
        self.assertEqual(
            (bounces["level"], bounces["mailbox"], bounces["stats"]), ("ok", "i2g@ucmerced.edu", {"listed": 3})
        )
        self.assertIsNotNone(bounces["next_scan_at"])
        self.assertEqual(summary["monitoring_began"], email.created_at)
