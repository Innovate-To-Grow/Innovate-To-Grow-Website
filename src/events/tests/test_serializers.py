"""
Serializer tests for events app.
"""

from django.test import TestCase
from datetime import date, time
from rest_framework.exceptions import ValidationError
from ..models import Event, Program, Track, Presentation, TrackWinner, SpecialAward
from ..serializers import (
    EventReadSerializer,
    EventSyncSerializer,
    PresentationSyncSerializer,
    TrackSyncSerializer,
    ProgramSyncSerializer,
    ExpoRowSerializer,
    ReceptionRowSerializer,
    WinnersSerializer,
    BasicInfoSerializer,
)


class EventReadSerializerTest(TestCase):
    """Test EventReadSerializer."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            upper_bullet_points=["Point 1", "Point 2"],
            lower_bullet_points=["Lower 1"],
            expo_table=[{"time": "10:00 AM", "room": "A", "description": "Expo"}],
            reception_table=[{"time": "5:00 PM", "room": "B", "description": "Reception"}],
            is_published=True,
        )

    def test_serialize_complete_event_with_nested_data(self):
        """Test serialization of complete event with nested data."""
        program = Program.objects.create(
            event=self.event,
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
        winner = TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Team Alpha",
        )
        award = SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Team Beta",
        )

        serializer = EventReadSerializer(self.event)
        data = serializer.data

        # Basic fields
        self.assertEqual(data['event_name'], "Test Event")
        self.assertEqual(data['event_date'], "2024-06-15")
        self.assertEqual(data['event_time'], "09:00:00")
        self.assertEqual(data['upper_bullet_points'], ["Point 1", "Point 2"])
        self.assertEqual(data['lower_bullet_points'], ["Lower 1"])
        self.assertEqual(data['expo_table'], [{"time": "10:00 AM", "room": "A", "description": "Expo"}])
        self.assertEqual(data['reception_table'], [{"time": "5:00 PM", "room": "B", "description": "Reception"}])
        self.assertTrue(data['is_published'])

        # Nested data
        self.assertEqual(len(data['programs']), 1)
        self.assertEqual(data['programs'][0]['program_name'], "CSE Program")
        self.assertEqual(len(data['programs'][0]['tracks']), 1)
        self.assertEqual(data['programs'][0]['tracks'][0]['track_name'], "Track 1")
        self.assertEqual(len(data['programs'][0]['tracks'][0]['presentations']), 1)
        self.assertEqual(data['programs'][0]['tracks'][0]['presentations'][0]['team_id'], "CSE-314")

        # Winners
        self.assertEqual(len(data['track_winners']), 1)
        self.assertEqual(data['track_winners'][0]['track_name'], "Track 1")
        self.assertEqual(len(data['special_awards']), 1)
        self.assertEqual(data['special_awards'][0]['program_name'], "CSE Program")

    def test_serialize_with_empty_programs(self):
        """Test serialization with empty programs/tracks/presentations."""
        serializer = EventReadSerializer(self.event)
        data = serializer.data
        self.assertEqual(data['programs'], [])
        self.assertEqual(data['track_winners'], [])
        self.assertEqual(data['special_awards'], [])

    def test_json_field_serialization(self):
        """Test JSON field serialization."""
        serializer = EventReadSerializer(self.event)
        data = serializer.data
        self.assertIsInstance(data['upper_bullet_points'], list)
        self.assertIsInstance(data['lower_bullet_points'], list)
        self.assertIsInstance(data['expo_table'], list)
        self.assertIsInstance(data['reception_table'], list)

    def test_read_only_fields(self):
        """Test read-only fields (event_uuid, created_at, updated_at)."""
        serializer = EventReadSerializer(self.event)
        data = serializer.data
        self.assertIn('event_uuid', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)
        # Verify read-only fields contain the correct values from the model
        original_uuid = str(self.event.event_uuid)
        self.assertEqual(data['event_uuid'], original_uuid)
        # Read-only fields should be present and match model values
        # (EventReadSerializer is read-only, so we can't test modification)


class EventSyncSerializerTest(TestCase):
    """Test EventSyncSerializer."""

    def test_validation_with_all_sections(self):
        """Test validation with all sections provided."""
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
                'upper_bullet_points': ['Point 1'],
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
            'expo_table': [{'time': '10:00 AM', 'description': 'Expo'}],
            'reception_table': [{'time': '5:00 PM', 'description': 'Reception'}],
            'winners': {
                'track_winners': [{'track_name': 'Track 1', 'winner_name': 'Winner'}],
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_partial_sections(self):
        """Test validation with partial sections."""
        # Only basic_info
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

        # Only schedule
        payload = {
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
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def test_validation_requires_at_least_one_section(self):
        """Test validation requires at least one section."""
        payload = {}
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_basic_info_validation(self):
        """Test basic_info validation (required fields)."""
        # Missing event_name
        payload = {
            'basic_info': {
                'event_date': '2024-06-15',
                'event_time': '09:00:00',
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        # Missing event_date
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_time': '09:00:00',
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        # Missing event_time
        payload = {
            'basic_info': {
                'event_name': 'Test Event',
                'event_date': '2024-06-15',
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())


class PresentationSyncSerializerTest(TestCase):
    """Test PresentationSyncSerializer."""

    def test_validation_for_regular_presentation(self):
        """Test validation for regular presentation (team_name required)."""
        data = {
            'order': 1,
            'team_name': 'Team Alpha',
            'project_title': 'Amazing Project',
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_for_regular_presentation_missing_team_name(self):
        """Test validation fails for regular presentation without team_name."""
        data = {
            'order': 1,
            'project_title': 'Amazing Project',
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('team_name', serializer.errors)

    def test_validation_for_break_entry_in_title(self):
        """Test validation for break entry (team_name optional when project_title contains 'break')."""
        data = {
            'order': 1,
            'project_title': 'Break',
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_for_break_entry_in_organization(self):
        """Test validation for break entry (team_name optional when organization is 'break')."""
        data = {
            'order': 1,
            'project_title': 'Lunch',
            'organization': 'break',
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_order_validation(self):
        """Test order validation (must be >= 1)."""
        data = {
            'order': 0,
            'team_name': 'Team Alpha',
            'project_title': 'Project',
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('order', serializer.errors)

    def test_project_title_required(self):
        """Test project_title required."""
        data = {
            'order': 1,
            'team_name': 'Team Alpha',
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('project_title', serializer.errors)


class TrackSyncSerializerTest(TestCase):
    """Test TrackSyncSerializer."""

    def test_validation_track_name_room_required(self):
        """Test validation (track_name, room required)."""
        data = {
            'track_name': 'Track 1',
            'room': 'Room A',
            'presentations': [],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_missing_track_name(self):
        """Test validation fails without track_name."""
        data = {
            'room': 'Room A',
            'presentations': [],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_start_time_optional(self):
        """Test start_time optional/nullable."""
        data = {
            'track_name': 'Track 1',
            'room': 'Room A',
            'start_time': None,
            'presentations': [],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_presentations_array_validation(self):
        """Test presentations array validation."""
        data = {
            'track_name': 'Track 1',
            'room': 'Room A',
            'presentations': [{
                'order': 1,
                'team_name': 'Team Alpha',
                'project_title': 'Project',
            }],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class ProgramSyncSerializerTest(TestCase):
    """Test ProgramSyncSerializer."""

    def test_validation_program_name_required(self):
        """Test validation (program_name required)."""
        data = {
            'program_name': 'CSE Program',
            'tracks': [],
        }
        serializer = ProgramSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_missing_program_name(self):
        """Test validation fails without program_name."""
        data = {
            'tracks': [],
        }
        serializer = ProgramSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_tracks_array_validation(self):
        """Test tracks array validation."""
        data = {
            'program_name': 'CSE Program',
            'tracks': [{
                'track_name': 'Track 1',
                'room': 'Room A',
                'presentations': [],
            }],
        }
        serializer = ProgramSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class ExpoRowSerializerTest(TestCase):
    """Test ExpoRowSerializer."""

    def test_validation_with_time_and_description(self):
        """Test validation with time and description."""
        data = {
            'time': '10:00 AM',
            'description': 'Expo start',
        }
        serializer = ExpoRowSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_allows_empty_rows(self):
        """Test validation allows empty rows."""
        data = {}
        serializer = ExpoRowSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_requires_time_when_description_provided(self):
        """Test validation requires time when description provided."""
        data = {
            'description': 'Expo start',
        }
        serializer = ExpoRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('time', serializer.errors)

    def test_validation_requires_description_when_time_provided(self):
        """Test validation requires description when time provided."""
        data = {
            'time': '10:00 AM',
        }
        serializer = ExpoRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('description', serializer.errors)


class ReceptionRowSerializerTest(TestCase):
    """Test ReceptionRowSerializer."""

    def test_validation_with_time_and_description(self):
        """Test validation with time and description."""
        data = {
            'time': '5:00 PM',
            'description': 'Reception',
        }
        serializer = ReceptionRowSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_allows_empty_rows(self):
        """Test validation allows empty rows."""
        data = {}
        serializer = ReceptionRowSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_requires_time_when_description_provided(self):
        """Test validation requires time when description provided."""
        data = {
            'description': 'Reception',
        }
        serializer = ReceptionRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('time', serializer.errors)

    def test_validation_requires_description_when_time_provided(self):
        """Test validation requires description when time provided."""
        data = {
            'time': '5:00 PM',
        }
        serializer = ReceptionRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('description', serializer.errors)


class WinnersSerializerTest(TestCase):
    """Test WinnersSerializer."""

    def test_validation_with_track_winners(self):
        """Test validation with track_winners."""
        data = {
            'track_winners': [
                {'track_name': 'Track 1', 'winner_name': 'Winner 1'},
            ],
        }
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_special_awards(self):
        """Test validation with special_awards."""
        data = {
            'special_awards': [
                {'program_name': 'CSE Program', 'award_winner': 'Award Winner'},
            ],
        }
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_both(self):
        """Test validation with both."""
        data = {
            'track_winners': [
                {'track_name': 'Track 1', 'winner_name': 'Winner 1'},
            ],
            'special_awards': [
                {'program_name': 'CSE Program', 'award_winner': 'Award Winner'},
            ],
        }
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_empty_winners(self):
        """Test validation with empty winners."""
        data = {}
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

