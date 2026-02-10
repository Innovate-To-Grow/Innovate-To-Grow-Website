"""
Tests for Event sheet export API.
"""

from datetime import UTC, time, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Event, Presentation, Program, SpecialAward, Track, TrackWinner


def _iso_utc(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class EventSheetExportAPIViewTest(TestCase):
    """Test GET /api/events/sync/export/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("events:event-sync-export")
        self.api_key = "test-api-key-123"

    def _auth(self):
        self.client.credentials(HTTP_X_API_KEY=self.api_key)

    def _create_live_event(self):
        event = Event.objects.create(
            event_name="Fall 2026 I2G Event",
            event_date_time=timezone.now(),
            slug="fall-2026-i2g-event",
            is_published=True,
            is_live=True,
            upper_bullet_points=["Upper 1", "Upper 2"],
            lower_bullet_points=["Lower 1"],
            expo_table=[
                {"time": "Room:", "room": "", "description": "Conference Center"},
                {"time": "9:00 AM", "room": "Conference Center", "description": "Registration"},
            ],
            reception_table=[
                {"time": "Room:", "room": "", "description": "Conference Center"},
                {"time": "5:00 PM", "room": "Conference Center", "description": "Reception"},
            ],
        )

        program_b = Program.objects.create(event=event, program_name="Program B", order=2)
        program_a = Program.objects.create(event=event, program_name="Program A", order=1)

        track_a2 = Track.objects.create(
            program=program_a,
            track_name="Track A2",
            room="GLCR 160",
            start_time=time(13, 0),
            order=2,
        )
        track_a1 = Track.objects.create(
            program=program_a,
            track_name="Track A1",
            room="GLCR 155",
            start_time=time(13, 0),
            order=1,
        )

        Presentation.objects.create(
            track=track_a1,
            order=2,
            team_id=None,
            team_name=None,
            project_title="Break",
            organization="Break",
            abstract="",
        )
        Presentation.objects.create(
            track=track_a1,
            order=1,
            team_id="A-101",
            team_name="Team A101",
            project_title="Project Alpha",
            organization="Org Alpha",
            abstract="Alpha abstract",
        )
        Presentation.objects.create(
            track=track_a2,
            order=1,
            team_id="A-201",
            team_name="Team A201",
            project_title="Project Beta",
            organization="Org Beta",
            abstract="Beta abstract",
        )

        track_b1 = Track.objects.create(
            program=program_b,
            track_name="Track B1",
            room="GLCR 150",
            start_time=time(13, 30),
            order=1,
        )
        Presentation.objects.create(
            track=track_b1,
            order=1,
            team_id="B-101",
            team_name="Team B101",
            project_title="Project Gamma",
            organization="Org Gamma",
            abstract=None,
        )

        TrackWinner.objects.create(event=event, track_name="Track A1", winner_name="Team A101")
        SpecialAward.objects.create(event=event, program_name="Program A", award_winner="Team A201")

        return event

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_requires_api_key_authentication(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_rejects_invalid_api_key(self):
        self.client.credentials(HTTP_X_API_KEY="invalid-key")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_returns_404_when_no_live_event(self):
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_full_mode_returns_sheet_friendly_payload(self):
        event = self._create_live_event()
        self._auth()

        response = self.client.get(self.url, {"mode": "full"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["meta"]["source"], "i2g-db")
        self.assertEqual(response.data["meta"]["scope"], "live_event")
        self.assertEqual(response.data["meta"]["mode"], "full")
        self.assertTrue(response.data["meta"]["delta_changed"])
        self.assertEqual(response.data["meta"]["event"]["event_uuid"], str(event.event_uuid))
        self.assertEqual(response.data["meta"]["event"]["slug"], event.slug)
        self.assertEqual(response.data["meta"]["event"]["event_name"], event.event_name)

        worksheets = response.data["worksheets"]
        self.assertEqual(
            set(worksheets.keys()),
            {
                "event_basic",
                "event_bullets",
                "event_expo",
                "event_reception",
                "event_schedule",
                "event_track_winners",
                "event_special_awards",
            },
        )

        event_basic = worksheets["event_basic"][0]
        self.assertEqual(event_basic["event_uuid"], str(event.event_uuid))
        self.assertEqual(event_basic["event_slug"], event.slug)
        self.assertEqual(event_basic["event_name"], event.event_name)
        self.assertEqual(event_basic["is_published"], True)
        self.assertEqual(event_basic["is_live"], True)
        self.assertTrue(event_basic["updated_at"].endswith("Z"))

        event_bullets = worksheets["event_bullets"]
        self.assertEqual(event_bullets[0]["section"], "upper")
        self.assertEqual(event_bullets[0]["position"], 1)
        self.assertEqual(event_bullets[-1]["section"], "lower")

        schedule = worksheets["event_schedule"]
        self.assertGreaterEqual(len(schedule), 4)
        self.assertEqual(schedule[0]["program_name"], "Program A")
        self.assertEqual(schedule[0]["program_order"], 1)
        self.assertEqual(schedule[0]["track_name"], "Track A1")
        self.assertEqual(schedule[0]["track_order"], 1)
        self.assertEqual(schedule[0]["presentation_order"], 1)
        self.assertEqual(schedule[0]["team_id"], "A-101")
        self.assertFalse(schedule[0]["is_break"])

        break_row = [row for row in schedule if row["project_title"] == "Break"][0]
        self.assertTrue(break_row["is_break"])
        self.assertEqual(break_row["team_id"], "")
        self.assertEqual(break_row["team_name"], "")

        track_winners = worksheets["event_track_winners"]
        self.assertEqual(len(track_winners), 1)
        self.assertEqual(track_winners[0]["position"], 1)
        self.assertEqual(track_winners[0]["track_name"], "Track A1")

        special_awards = worksheets["event_special_awards"]
        self.assertEqual(len(special_awards), 1)
        self.assertEqual(special_awards[0]["position"], 1)
        self.assertEqual(special_awards[0]["program_name"], "Program A")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_requires_since(self):
        self._create_live_event()
        self._auth()

        response = self.client.get(self.url, {"mode": "delta"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_rejects_invalid_since(self):
        self._create_live_event()
        self._auth()

        response = self.client.get(self.url, {"mode": "delta", "since": "not-a-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_returns_empty_worksheets_when_no_change(self):
        event = self._create_live_event()
        self._auth()

        since = _iso_utc(event.updated_at + timedelta(minutes=5))
        response = self.client.get(self.url, {"mode": "delta", "since": since})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["meta"]["mode"], "delta")
        self.assertFalse(response.data["meta"]["delta_changed"])

        worksheets = response.data["worksheets"]
        for key in worksheets:
            self.assertEqual(worksheets[key], [])

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_returns_full_snapshot_when_changed(self):
        event = self._create_live_event()
        self._auth()

        since = _iso_utc(event.updated_at - timedelta(minutes=5))
        response = self.client.get(self.url, {"mode": "delta", "since": since})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["meta"]["mode"], "delta")
        self.assertTrue(response.data["meta"]["delta_changed"])
        self.assertEqual(len(response.data["worksheets"]["event_basic"]), 1)
        self.assertGreater(len(response.data["worksheets"]["event_schedule"]), 0)
