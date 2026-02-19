"""
Serializer tests for table and winners serializers
(ExpoRowSerializer, ReceptionRowSerializer, WinnersSerializer).
"""

from django.test import TestCase

from ...serializers import (
    ExpoRowSerializer,
    ReceptionRowSerializer,
    WinnersSerializer,
)


class ExpoRowSerializerTest(TestCase):
    """Test ExpoRowSerializer."""

    def test_validation_with_time_and_description(self):
        """Test validation with time and description."""
        data = {
            "time": "10:00 AM",
            "description": "Expo start",
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
            "description": "Expo start",
        }
        serializer = ExpoRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("time", serializer.errors)

    def test_validation_requires_description_when_time_provided(self):
        """Test validation requires description when time provided."""
        data = {
            "time": "10:00 AM",
        }
        serializer = ExpoRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("description", serializer.errors)


class ReceptionRowSerializerTest(TestCase):
    """Test ReceptionRowSerializer."""

    def test_validation_with_time_and_description(self):
        """Test validation with time and description."""
        data = {
            "time": "5:00 PM",
            "description": "Reception",
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
            "description": "Reception",
        }
        serializer = ReceptionRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("time", serializer.errors)

    def test_validation_requires_description_when_time_provided(self):
        """Test validation requires description when time provided."""
        data = {
            "time": "5:00 PM",
        }
        serializer = ReceptionRowSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("description", serializer.errors)


class WinnersSerializerTest(TestCase):
    """Test WinnersSerializer."""

    def test_validation_with_track_winners(self):
        """Test validation with track_winners."""
        data = {
            "track_winners": [
                {"track_name": "Track 1", "winner_name": "Winner 1"},
            ],
        }
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_special_awards(self):
        """Test validation with special_awards."""
        data = {
            "special_awards": [
                {"program_name": "CSE Program", "award_winner": "Award Winner"},
            ],
        }
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_both(self):
        """Test validation with both."""
        data = {
            "track_winners": [
                {"track_name": "Track 1", "winner_name": "Winner 1"},
            ],
            "special_awards": [
                {"program_name": "CSE Program", "award_winner": "Award Winner"},
            ],
        }
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_empty_winners(self):
        """Test validation with empty winners."""
        data = {}
        serializer = WinnersSerializer(data=data)
        self.assertTrue(serializer.is_valid())
