"""
View tests for events app.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, time, datetime
from ..models import Event, Program, Track, Presentation, TrackWinner, SpecialAward


class EventRetrieveAPIViewTest(TestCase):
    """Test EventRetrieveAPIView (GET /api/events/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse('events:event-retrieve')

    def test_returns_published_event_when_one_exists(self):
        """Test returns published event when one exists."""
        published_event = Event.objects.create(
            event_name="Published Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=True,
        )
        unpublished_event = Event.objects.create(
            event_name="Unpublished Event",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
            is_published=False,
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['event_name'], "Published Event")
        self.assertEqual(response.data['event_uuid'], str(published_event.event_uuid))

    def test_returns_most_recent_event_when_no_published_events_exist(self):
        """Test returns most recent event when no published events exist."""
        event1 = Event.objects.create(
            event_name="Event 1",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=False,
        )
        event2 = Event.objects.create(
            event_name="Event 2",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
            is_published=False,
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return most recent (event2, created later)
        self.assertEqual(response.data['event_name'], "Event 2")

    def test_returns_404_when_no_events_exist(self):
        """Test returns 404 when no events exist."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)

    def test_response_structure_matches_event_read_serializer(self):
        """Test response structure matches EventReadSerializer."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=True,
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check all expected fields are present
        self.assertIn('event_uuid', response.data)
        self.assertIn('event_name', response.data)
        self.assertIn('event_date', response.data)
        self.assertIn('event_time', response.data)
        self.assertIn('upper_bullet_points', response.data)
        self.assertIn('lower_bullet_points', response.data)
        self.assertIn('expo_table', response.data)
        self.assertIn('reception_table', response.data)
        self.assertIn('is_published', response.data)
        self.assertIn('programs', response.data)
        self.assertIn('track_winners', response.data)
        self.assertIn('special_awards', response.data)
        self.assertIn('created_at', response.data)
        self.assertIn('updated_at', response.data)

    def test_nested_data_structure(self):
        """Test nested data structure (programs → tracks → presentations)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=True,
        )
        program = Program.objects.create(
            event=event,
            program_name="CSE Program",
        )
        track = Track.objects.create(
            program=program,
            track_name="Track 1",
            room="Room A",
            start_time=time(13, 0),
        )
        presentation = Presentation.objects.create(
            track=track,
            order=1,
            team_id="CSE-314",
            team_name="Team Alpha",
            project_title="Amazing Project",
            organization="Org A",
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['programs']), 1)
        self.assertEqual(response.data['programs'][0]['program_name'], "CSE Program")
        self.assertEqual(len(response.data['programs'][0]['tracks']), 1)
        self.assertEqual(response.data['programs'][0]['tracks'][0]['track_name'], "Track 1")
        self.assertEqual(len(response.data['programs'][0]['tracks'][0]['presentations']), 1)
        self.assertEqual(response.data['programs'][0]['tracks'][0]['presentations'][0]['team_id'], "CSE-314")

    def test_json_fields_serialized_correctly(self):
        """Test JSON fields serialized correctly."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            upper_bullet_points=["Point 1", "Point 2"],
            lower_bullet_points=["Lower 1"],
            expo_table=[{"time": "10:00 AM", "room": "A", "description": "Expo"}],
            reception_table=[{"time": "5:00 PM", "room": "B", "description": "Reception"}],
            is_published=True,
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['upper_bullet_points'], ["Point 1", "Point 2"])
        self.assertEqual(response.data['lower_bullet_points'], ["Lower 1"])
        self.assertEqual(len(response.data['expo_table']), 1)
        self.assertEqual(len(response.data['reception_table']), 1)

    def test_multiple_events_published_vs_unpublished_priority(self):
        """Test multiple events (published vs unpublished priority)."""
        # Create unpublished event first (older)
        unpublished = Event.objects.create(
            event_name="Unpublished",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=False,
        )
        # Create published event later
        published = Event.objects.create(
            event_name="Published",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
            is_published=True,
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return published event even if it's newer
        self.assertEqual(response.data['event_name'], "Published")


class EventSyncAPIViewTest(TestCase):
    """Test EventSyncAPIView (POST /api/events/sync/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse('events:event-sync')
        self.api_key = 'test-api-key-123'

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_requires_api_key_authentication(self):
        """Test requires API key authentication (401 without key)."""
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
            },
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_rejects_invalid_api_key(self):
        """Test rejects invalid API key (401 with wrong key)."""
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
            },
        }
        self.client.credentials(HTTP_X_API_KEY='wrong-key')
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_creates_new_event_when_none_exists(self):
        """Test creates new event when none exists (with basic_info)."""
        payload = {
            'basic_info': {
                'event_name': 'New Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
                'upper_bullet_points': ['Point 1'],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify event was created
        event = Event.objects.get(event_name='New Event')
        self.assertEqual(event.event_name, 'New Event')
        self.assertEqual(event.upper_bullet_points, ['Point 1'])

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_updates_existing_event(self):
        """Test updates existing event."""
        event = Event.objects.create(
            event_name="Old Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'basic_info': {
                'event_name': 'Updated Event',
                'event_date': '2024-06-16',
                'event_time': '10:00:00',
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify event was updated
        event.refresh_from_db()
        self.assertEqual(event.event_name, 'Updated Event')
        self.assertEqual(event.event_date, date(2024, 6, 16))

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_processes_basic_info_only(self):
        """Test processes basic_info only."""
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
                'upper_bullet_points': ['Point 1'],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event = Event.objects.get()
        self.assertEqual(event.event_name, 'Test Event')
        self.assertEqual(event.upper_bullet_points, ['Point 1'])

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_processes_schedule_only(self):
        """Test processes schedule only (creates full hierarchy)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'schedule': [{
                'program_name': 'CSE Program',
                'tracks': [{
                    'track_name': 'Track 1',
                    'room': 'Room A',
                    'start_time': '13:00:00',
                    'presentations': [{
                        'order': 1,
                        'team_id': 'CSE-314',
                        'team_name': 'Team Alpha',
                        'project_title': 'Amazing Project',
                        'organization': 'Org A',
                    }],
                }],
            }],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify hierarchy was created
        program = event.programs.get(program_name='CSE Program')
        track = program.tracks.get(track_name='Track 1')
        presentation = track.presentations.get(order=1)
        self.assertEqual(presentation.team_id, 'CSE-314')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_processes_expo_table_only(self):
        """Test processes expo_table only."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'expo_table': [
                {'time': 'Room:', 'description': 'Room A'},
                {'time': '10:00 AM', 'description': 'Expo start'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        self.assertEqual(len(event.expo_table), 1)
        self.assertEqual(event.expo_table[0]['time'], '10:00 AM')
        self.assertEqual(event.expo_table[0]['room'], 'Room A')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_processes_reception_table_only(self):
        """Test processes reception_table only."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'reception_table': [
                {'time': 'Room:', 'description': 'Room B'},
                {'time': '5:00 PM', 'description': 'Reception'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        self.assertEqual(len(event.reception_table), 1)
        self.assertEqual(event.reception_table[0]['time'], '5:00 PM')
        self.assertEqual(event.reception_table[0]['room'], 'Room B')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_processes_winners_only(self):
        """Test processes winners only."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'winners': {
                'track_winners': [
                    {'track_name': 'Track 1', 'winner_name': 'Winner 1'},
                ],
                'special_awards': [
                    {'program_name': 'CSE Program', 'award_winner': 'Award Winner'},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertEqual(event.track_winners.count(), 1)
        self.assertEqual(event.special_awards.count(), 1)

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_processes_multiple_sections_together(self):
        """Test processes multiple sections together."""
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
            },
            'schedule': [{
                'program_name': 'CSE Program',
                'tracks': [{
                    'track_name': 'Track 1',
                    'room': 'Room A',
                    'presentations': [{
                        'order': 1,
                        'team_name': 'Team Alpha',
                        'project_title': 'Project',
                    }],
                }],
            }],
            'expo_table': [
                {'time': 'Room:', 'description': 'Room A'},
                {'time': '10:00 AM', 'description': 'Expo'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event = Event.objects.get()
        self.assertEqual(event.event_name, 'Test Event')
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(len(event.expo_table), 1)

    @override_settings(EVENTS_API_KEY='test-api-key-123')
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
            'schedule': [{
                'program_name': 'New Program',
                'tracks': [{
                    'track_name': 'Track 1',
                    'room': 'Room A',
                    'presentations': [{
                        'order': 1,
                        # Missing team_name and project_title
                    }],
                }],
            }],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        # Should fail validation
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Verify existing program was not deleted (transaction rolled back)
        event.refresh_from_db()
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(event.programs.first().program_name, 'Existing Program')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
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
            'schedule': [{
                'program_name': 'New Program',
                'tracks': [{
                    'track_name': 'Track 1',
                    'room': 'Room A',
                    'presentations': [{
                        'order': 1,
                        'team_name': 'Team Alpha',
                        'project_title': 'Project',
                    }],
                }],
            }],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify old program was deleted
        event.refresh_from_db()
        self.assertFalse(Program.objects.filter(id=old_program.id).exists())
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(event.programs.first().program_name, 'New Program')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_deletes_existing_winners_when_winners_updated(self):
        """Test deletes existing winners when winners updated."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        old_winner = TrackWinner.objects.create(
            event=event,
            track_name='Old Track',
            winner_name='Old Winner',
        )
        
        payload = {
            'winners': {
                'track_winners': [
                    {'track_name': 'New Track', 'winner_name': 'New Winner'},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify old winner was deleted
        self.assertFalse(TrackWinner.objects.filter(id=old_winner.id).exists())
        self.assertEqual(event.track_winners.count(), 1)
        self.assertEqual(event.track_winners.first().track_name, 'New Track')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_time_formatting_gmt_timestamp(self):
        """Test time formatting in expo_table (GMT timestamp → 12-hour AM/PM)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'expo_table': [
                {'time': 'Room:', 'description': 'Room A'},
                {'time': '2024-06-15T14:30:00Z', 'description': 'Expo start'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        # 14:30 UTC should be formatted as 2:30 PM (or adjusted for timezone)
        self.assertIn('PM', event.expo_table[0]['time'])

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_time_formatting_without_am_pm(self):
        """Test time formatting adds AM/PM when missing."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'expo_table': [
                {'time': 'Room:', 'description': 'Room A'},
                {'time': '14:30', 'description': 'Expo start'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        # Should add AM/PM
        self.assertIn('PM', event.expo_table[0]['time'])

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_room_extraction_from_header_rows(self):
        """Test room extraction from header rows (time="Room:")."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'expo_table': [
                {'time': 'Room:', 'description': 'Room A'},
                {'time': '10:00 AM', 'description': 'Expo start'},
                {'time': '11:00 AM', 'description': 'Expo continue'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        # Both rows should have room from header
        self.assertEqual(event.expo_table[0]['room'], 'Room A')
        self.assertEqual(event.expo_table[1]['room'], 'Room A')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_room_application_to_subsequent_rows(self):
        """Test room application to subsequent rows."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'expo_table': [
                {'time': 'Room:', 'description': 'Room A'},
                {'time': '10:00 AM', 'description': 'First'},
                {'time': '11:00 AM', 'description': 'Second'},
                {'time': 'Room:', 'description': 'Room B'},
                {'time': '12:00 PM', 'description': 'Third'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        # First two rows should have Room A, third should have Room B
        self.assertEqual(event.expo_table[0]['room'], 'Room A')
        self.assertEqual(event.expo_table[1]['room'], 'Room A')
        self.assertEqual(event.expo_table[2]['room'], 'Room B')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_handles_missing_room_headers(self):
        """Test handles missing room headers."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'expo_table': [
                {'time': '10:00 AM', 'room': 'Room A', 'description': 'Expo start'},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        event.refresh_from_db()
        # Should use room from row field
        self.assertEqual(event.expo_table[0]['room'], 'Room A')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_break_handling_null_team_fields_allowed(self):
        """Test break handling (null team_id/team_name allowed)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        
        payload = {
            'schedule': [{
                'program_name': 'CSE Program',
                'tracks': [{
                    'track_name': 'Track 1',
                    'room': 'Room A',
                    'presentations': [{
                        'order': 1,
                        'project_title': 'Break',
                        # No team_name or team_id
                    }],
                }],
            }],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        presentation = event.programs.first().tracks.first().presentations.first()
        self.assertIsNone(presentation.team_id)
        self.assertIsNone(presentation.team_name)
        self.assertEqual(presentation.project_title, 'Break')

    @override_settings(EVENTS_API_KEY='test-api-key-123')
    def test_response_includes_event_uuid(self):
        """Test response includes event_uuid."""
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('event_uuid', response.data)
        
        event = Event.objects.get()
        self.assertEqual(response.data['event_uuid'], str(event.event_uuid))

