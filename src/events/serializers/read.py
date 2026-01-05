"""
Read-only serializers for Event frontend consumption.
"""

from rest_framework import serializers

from ..models import Event, Presentation, Program, SpecialAward, Track, TrackWinner


class PresentationSerializer(serializers.ModelSerializer):
    """Serializer for Presentation model."""

    class Meta:
        model = Presentation
        fields = [
            "order",
            "team_id",
            "team_name",
            "project_title",
            "organization",
        ]
        read_only_fields = ["id"]


class TrackSerializer(serializers.ModelSerializer):
    """Serializer for Track model with nested presentations."""

    presentations = PresentationSerializer(many=True, read_only=True)

    class Meta:
        model = Track
        fields = [
            "track_name",
            "room",
            "start_time",
            "presentations",
        ]
        read_only_fields = ["id"]


class ProgramSerializer(serializers.ModelSerializer):
    """Serializer for Program model with nested tracks."""

    tracks = TrackSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = [
            "program_name",
            "tracks",
        ]
        read_only_fields = ["id"]


class TrackWinnerSerializer(serializers.ModelSerializer):
    """Serializer for TrackWinner model."""

    class Meta:
        model = TrackWinner
        fields = [
            "track_name",
            "winner_name",
        ]
        read_only_fields = ["id"]


class SpecialAwardSerializer(serializers.ModelSerializer):
    """Serializer for SpecialAward model."""

    class Meta:
        model = SpecialAward
        fields = [
            "program_name",
            "award_winner",
        ]
        read_only_fields = ["id"]


class EventReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for frontend consumption."""

    programs = ProgramSerializer(many=True, read_only=True)
    track_winners = TrackWinnerSerializer(many=True, read_only=True)
    special_awards = SpecialAwardSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            "event_uuid",
            "event_name",
            "event_date",
            "event_time",
            "upper_bullet_points",
            "lower_bullet_points",
            "expo_table",
            "reception_table",
            "is_published",
            "programs",
            "track_winners",
            "special_awards",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["event_uuid", "created_at", "updated_at"]

