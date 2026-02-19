"""
View tests for events app — EventSyncAPIView update and rollback behavior.
"""

from datetime import date, time

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event, Program, TrackWinner


class EventSyncUpdatesTest(TestCase):
    """Test EventSyncAPIView update/rollback behavior (POST /api/events/sync/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_atomic_transaction_rollback_on_error(self):
        """Test atomic transaction (rollback on error)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        program = Program.objects.create(
            event=event,
            program_name="Existing Program",
        )

        # Invalid payload (missing required field in presentation)
        payload = {
            "schedule": [
                {
                    "program_name": "New Program",
                    "tracks": [
                        {
                            "track_name": "Track 1",
                            "room": "Room A",
                            "presentations": [
                                {
                                    "order": 1,
                                    # Missing team_name and project_title
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        # Should fail validation
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verify existing program was not deleted (transaction rolled back)
        event.refresh_from_db()
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(event.programs.first().program_name, "Existing Program")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_deletes_existing_programs_when_schedule_updated(self):
        """Test deletes existing programs when schedule updated."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        old_program = Program.objects.create(
            event=event,
            program_name="Old Program",
        )

        payload = {
            "schedule": [
                {
                    "program_name": "New Program",
                    "tracks": [
                        {
                            "track_name": "Track 1",
                            "room": "Room A",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_name": "Team Alpha",
                                    "project_title": "Project",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify old program was deleted
        event.refresh_from_db()
        self.assertFalse(Program.objects.filter(id=old_program.id).exists())
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(event.programs.first().program_name, "New Program")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_deletes_existing_winners_when_winners_updated(self):
        """Test deletes existing winners when winners updated."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        old_winner = TrackWinner.objects.create(
            event=event,
            track_name="Old Track",
            winner_name="Old Winner",
        )

        payload = {
            "winners": {
                "track_winners": [
                    {"track_name": "New Track", "winner_name": "New Winner"},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify old winner was deleted
        self.assertFalse(TrackWinner.objects.filter(id=old_winner.id).exists())
        self.assertEqual(event.track_winners.count(), 1)
        self.assertEqual(event.track_winners.first().track_name, "New Track")
