"""``EmailMonitorState.scanned_since``: the lower bound of what the bounce scans have read continuously. The first scan
that saves a checkpoint sets it (an existing checkpoint: that less the overlap, never a retroactive claim), later
scans keep it, a scan that saved nothing leaves it unknown, and "Rescan since" lowers it."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailMonitorState
from apps.core.services.email.bounces.scanning import scanner, state
from apps.core.services.email.graph.mailbox import GraphReadError

from ..bounce_scan.test_bounce_scanner import READER, FakeReader, listed
from ..helpers import SENDER, monitoring_settings

SETTINGS = {"bounce_scan_overlap_seconds": 900, "bounce_initial_lookback_hours": 72}


class ScannedSinceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now().replace(microsecond=0)
        self.messages = [
            listed("human-1", subject="Hi", sender="person@example.com", received=self.now - timedelta(minutes=9))
        ]

    def scan(self, reader=None, *, now=None):
        reader = reader or FakeReader(self.messages, {})
        with patch(READER, return_value=(reader, SENDER, "")), monitoring_settings(**SETTINGS):
            return scanner.scan_mailbox(now=now or self.now)

    def row(self) -> EmailMonitorState:
        return EmailMonitorState.objects.get(mailbox=SENDER)

    def test_the_first_scan_sets_it_to_where_it_started_listing(self):
        self.assertEqual(self.scan().status, "ok")

        self.assertEqual(self.row().scanned_since, self.now - timedelta(hours=72))

    def test_an_existing_checkpoint_counts_only_from_the_checkpoint_less_the_overlap(self):
        checkpoint = self.now - timedelta(hours=1)
        state.state_for(SENDER)
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=checkpoint)

        self.scan()

        self.assertEqual(self.row().scanned_since, checkpoint - timedelta(seconds=900))

    def test_later_scans_keep_it(self):
        self.scan()
        first = self.row().scanned_since

        self.scan(now=self.now + timedelta(minutes=10))

        self.assertEqual(self.row().scanned_since, first)

    def test_a_first_scan_that_saved_no_checkpoint_leaves_it_unknown(self):
        outcome = self.scan(FakeReader(self.messages, {}, list_error=GraphReadError("refused")))

        self.assertEqual(outcome.status, "failed")
        self.assertIsNone(self.row().scanned_since)
        self.assertIsNone(self.row().checkpoint_at)

    def test_rescan_since_lowers_it_and_never_raises_it(self):
        self.scan()
        earlier = self.now - timedelta(days=6)

        self.assertEqual(state.rescan_since(SENDER, earlier, now=self.now).status, "moved")
        self.assertEqual(self.row().scanned_since, earlier)

        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=self.now)
        state.rescan_since(SENDER, self.now - timedelta(days=1), now=self.now)
        self.assertEqual(self.row().scanned_since, earlier)

    def test_rescan_since_without_coverage_starts_it_at_the_rescan_time(self):
        state.state_for(SENDER)
        since = self.now - timedelta(days=2)

        state.rescan_since(SENDER, since, now=self.now)

        self.assertEqual(self.row().scanned_since, since)
