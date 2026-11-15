from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailCategory, EmailMonitorState
from apps.core.services.email.bounces import ensure_scheduled
from apps.core.tests.services.email_monitoring.helpers import make_bounce, make_email, monitoring_settings
from apps.mail.services.email_monitoring.dashboard import health, log, scope


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

    def test_a_mailbox_paused_before_its_first_scan_is_paused_not_waiting(self):
        # Its first scan waits for Resume: "waiting for the first scan" would hide that someone paused it.
        never_scanned = {"last_run_finished_at": None, "last_success_at": None}
        self.assertEqual(self.level(paused=True, **never_scanned), "paused")
        self.assertEqual(self.level(paused=False, **never_scanned), "waiting")

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
