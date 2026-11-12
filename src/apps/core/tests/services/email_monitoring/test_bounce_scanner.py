"""The bounce processor's scans: incremental listing, candidate selection, checkpoint, lease and health, and its
handling of Microsoft's throttling and failures. Microsoft Graph is never contacted."""

import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import unquote

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, EmailMonitorState, EmailServiceConfig
from apps.core.services.email.bounces import scanner, source, state
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import SEND_AND_READ, create_graph_config
from apps.core.tests.services.test_email_graph import token_response

from .helpers import SENDER, make_email, monitoring_settings
from .ndr_samples import ORIGINAL_ID, exchange_ndr, personal_email

READER = "apps.core.services.email.bounces.scanner.active_reader"


def listed(graph_id, *, subject, sender, received):
    return {
        "id": graph_id,
        "subject": subject,
        "from": {"emailAddress": {"address": sender}},
        "receivedDateTime": received.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class FakeReader:
    """Stands in for ``GraphMailboxReader``: a fixed inbox, oldest first; records what was opened."""

    def __init__(self, messages, bodies, *, list_error=None, fetch_error=None):
        self.messages, self.bodies = messages, bodies
        self.list_error, self.fetch_error = list_error, fetch_error
        self.opened, self.since = [], []

    def list_received_since(self, folder, since, limit):
        if self.list_error:
            raise self.list_error
        self.since.append(since)
        selected = [m for m in self.messages if source.received_at(m) >= since.replace(microsecond=0)]
        return selected[:limit]

    def fetch_mime_head(self, message_id, max_bytes):
        if self.fetch_error:
            raise self.fetch_error
        self.opened.append(message_id)
        return self.bodies[message_id][:max_bytes], len(self.bodies[message_id]) > max_bytes


class ScannerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now().replace(microsecond=0)
        self.email = make_email(internet_message_id=ORIGINAL_ID, recipient="nobody@example.com")
        self.messages = [
            listed(
                "ndr-1",
                subject="Undeliverable: Hello",
                sender="postmaster@ucmerced.onmicrosoft.com",
                received=self.now - timedelta(minutes=30),
            ),
            listed(
                "human-1", subject="Question", sender="person@example.com", received=self.now - timedelta(minutes=20)
            ),
            listed(
                "human-2",
                subject="Undeliverable: my question",
                sender="person@example.com",
                received=self.now - timedelta(minutes=10),
            ),
        ]
        self.bodies = {"ndr-1": exchange_ndr(), "human-1": b"", "human-2": personal_email()}

    def scan(self, reader, **settings_changes):
        with patch(READER, return_value=(reader, SENDER, "")), monitoring_settings(**settings_changes):
            return scanner.scan_mailbox(now=self.now)

    def test_a_scan_opens_only_candidates_saves_their_bounces_and_moves_the_checkpoint(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader)

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(reader.opened, ["ndr-1", "human-2"])  # "Question" from a person is never opened
        self.assertEqual(outcome.stats["bounces"], 1)
        self.assertEqual((outcome.stats["matched"], outcome.stats["not_reports"]), (1, 1))
        self.assertEqual(EmailBounce.objects.get().email, self.email)
        monitor = EmailMonitorState.objects.get(mailbox=SENDER)
        self.assertEqual(monitor.checkpoint_at, self.now)
        self.assertEqual((monitor.consecutive_failures, monitor.lease_token), (0, None))
        self.assertIsNotNone(monitor.last_success_at)

    def test_the_first_scan_looks_back_and_later_ones_start_at_the_checkpoint_less_the_overlap(self):
        reader = FakeReader(self.messages, self.bodies)

        self.scan(reader, bounce_initial_lookback_hours=72, bounce_scan_overlap_seconds=900)
        self.scan(reader, bounce_initial_lookback_hours=72, bounce_scan_overlap_seconds=900)

        self.assertEqual(reader.since[0], self.now - timedelta(hours=72))
        self.assertEqual(reader.since[1], self.now - timedelta(seconds=900))

    def test_a_second_scan_never_opens_or_records_a_report_again(self):
        reader = FakeReader(self.messages, self.bodies)
        self.scan(reader)
        EmailMonitorState.objects.update(checkpoint_at=None)

        outcome = self.scan(reader)

        self.assertEqual(outcome.stats["already_processed"], 1)
        self.assertEqual(reader.opened.count("ndr-1"), 1)
        self.assertEqual(EmailBounce.objects.count(), 1)

    def test_a_busy_read_keeps_the_progress_and_waits_as_microsoft_asked(self):
        reader = FakeReader(self.messages, self.bodies, fetch_error=GraphReadBusy(90))

        outcome = self.scan(reader)

        self.assertEqual((outcome.status, outcome.retry_after), ("busy", 90))
        monitor = EmailMonitorState.objects.get(mailbox=SENDER)
        self.assertEqual(monitor.consecutive_failures, 0)
        self.assertIsNone(monitor.last_success_at)
        self.assertGreater(monitor.next_run_after, timezone.now())

    def test_a_refused_read_is_a_failed_scan_shown_on_the_state(self):
        reader = FakeReader([], {}, list_error=GraphReadError("Microsoft Graph denied access to i2g@ucmerced.edu."))

        outcome = self.scan(reader)
        self.scan(reader)

        self.assertEqual(outcome.status, "failed")
        monitor = EmailMonitorState.objects.get(mailbox=SENDER)
        self.assertEqual(monitor.consecutive_failures, 2)
        self.assertEqual(monitor.last_error, "Microsoft Graph denied access to i2g@ucmerced.edu.")
        self.assertIsNone(monitor.lease_token)

    def test_an_unexpected_error_is_recorded_by_type_only(self):
        reader = FakeReader([], {}, list_error=RuntimeError("detail that may echo request values"))

        outcome = self.scan(reader)

        self.assertEqual(outcome.error, "Unexpected RuntimeError")
        self.assertEqual(EmailMonitorState.objects.get().last_error, "Unexpected RuntimeError")

    def test_a_report_that_cannot_be_parsed_is_kept_as_unknown(self):
        reader = FakeReader(self.messages[:1], self.bodies)

        with patch("apps.core.services.email.bounces.scanner.parse_report", side_effect=ValueError("broken")):
            outcome = self.scan(reader)

        bounce = EmailBounce.objects.get()
        self.assertEqual((outcome.status, bounce.classification, bounce.recipient), ("ok", "unknown", ""))

    def test_the_message_budget_ends_a_scan_early_with_the_checkpoint_at_what_was_done(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader, bounce_scan_max_messages=1)

        self.assertEqual((outcome.status, reader.opened), ("partial", ["ndr-1"]))
        checkpoint = EmailMonitorState.objects.get().checkpoint_at
        self.assertEqual(checkpoint, self.now - timedelta(minutes=20))

    def test_the_time_budget_ends_a_scan_before_it_opens_more_reports(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader, bounce_scan_max_seconds=0)

        self.assertEqual((outcome.status, reader.opened), ("partial", []))

    def test_a_report_the_database_refuses_is_skipped_and_counted(self):
        from django.db import DataError

        reader = FakeReader(self.messages, self.bodies)

        with patch("apps.core.services.email.bounces.scanner.save_report", side_effect=DataError("bad data")):
            outcome = self.scan(reader)

        self.assertEqual((outcome.status, outcome.stats["unstorable"]), ("ok", 1))
        self.assertEqual(EmailMonitorState.objects.get().checkpoint_at, self.now)

    def test_a_paused_mailbox_is_skipped(self):
        state.set_paused(SENDER, True)
        reader = FakeReader(self.messages, self.bodies)

        self.assertEqual(self.scan(reader).status, "paused")
        self.assertEqual(reader.opened, [])

    def test_a_running_scan_holds_the_mailbox(self):
        state.state_for(SENDER)
        self.assertIsNotNone(state.acquire_lease(SENDER, self.now))

        self.assertEqual(self.scan(FakeReader(self.messages, self.bodies)).status, "locked")

    def test_an_expired_lease_is_taken_over(self):
        state.state_for(SENDER)
        state.acquire_lease(SENDER, self.now - timedelta(hours=2))

        self.assertEqual(self.scan(FakeReader(self.messages, self.bodies)).status, "ok")

    def test_switched_off_it_does_nothing(self):
        reader = FakeReader(self.messages, self.bodies)

        self.assertEqual(self.scan(reader, bounce_processing_enabled=False).status, "disabled")
        self.assertEqual(reader.opened, [])


class ActiveReaderTests(TestCase):
    def setUp(self):
        cache.clear()
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)

    def test_without_graph_bounce_processing_is_inactive(self):
        outcome = scanner.scan_mailbox()

        self.assertEqual((outcome.status, outcome.mailbox), ("inactive", ""))
        self.assertIn("not configured", outcome.error)

    def test_a_mailbox_outside_the_allow_list_is_never_read(self):
        create_graph_config(scope=("other@ucmerced.edu",), is_active=True, mailbox="other@ucmerced.edu")

        outcome = scanner.scan_mailbox()

        self.assertEqual((outcome.status, outcome.mailbox), ("inactive", "other@ucmerced.edu"))
        self.assertIn("allow-list", EmailMonitorState.objects.get(mailbox="other@ucmerced.edu").last_error)

    def test_a_mailbox_the_scope_lets_send_only_is_never_read(self):
        create_graph_config(scope=(SENDER,), permission="send", is_active=True, mailbox=SENDER)

        reader, mailbox, problem = scanner.active_reader()

        self.assertIsNone(reader)
        self.assertEqual(mailbox, SENDER)
        self.assertIn("does not grant read", problem)


class RealReaderTests(TestCase):
    """The scan through the real ``GraphMailboxReader``: its list request passes the transport's allow-list."""

    def setUp(self):
        cache.clear()
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        create_graph_config(scope=(SENDER,), permission=SEND_AND_READ, is_active=True, mailbox=SENDER)
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)
        make_email(internet_message_id=ORIGINAL_ID, recipient="nobody@example.com")
        self.requests = []
        received = timezone.now().replace(microsecond=0) - timedelta(minutes=5)
        self.listing = {
            "value": [
                listed(
                    "AAMkNDR1", subject="Undeliverable: Hello", sender="postmaster@x.onmicrosoft.com", received=received
                )
            ]
        }

    def fake_request(self, method, host, path, body, headers, *, timeout, max_bytes, user_agent):
        self.requests.append((method, host, path))
        if host == "login.microsoftonline.com":
            return token_response()
        if path.endswith("/$value"):
            return HttpResponse(200, {}, exchange_ndr())
        return HttpResponse(200, {}, json.dumps(self.listing).encode())

    def test_the_scan_lists_incrementally_reads_only_with_get_and_stores_the_bounce(self):
        with patch("apps.core.services.email.graph.transport.request", side_effect=self.fake_request):
            outcome = scanner.scan_mailbox()

        self.assertEqual(outcome.status, "ok")
        graph_requests = [request for request in self.requests if request[1] == "graph.microsoft.com"]
        self.assertEqual({method for method, _host, _path in graph_requests}, {"GET"})
        list_path = unquote(graph_requests[0][2])
        self.assertIn("/v1.0/users/i2g@ucmerced.edu/mailFolders/inbox/messages?", list_path)
        self.assertIn("$filter=receivedDateTime ge ", list_path)
        self.assertIn("$orderby=receivedDateTime asc", list_path)
        self.assertTrue(graph_requests[1][2].endswith("/messages/AAMkNDR1/$value"))
        self.assertEqual(EmailBounce.objects.get().match_method, "message_id")
