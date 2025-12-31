"""
Serializers for Event Management System.

Includes both sync serializer (for Google Sheets POST) and read serializer (for frontend).
"""

from rest_framework import serializers
from ..models import Event, Program, Track, Presentation, TrackWinner, SpecialAward


# ==================== Nested Serializers (for read) ====================

class PresentationSerializer(serializers.ModelSerializer):
    """Serializer for Presentation model."""

    class Meta:
        model = Presentation
        fields = [
            'order',
            'team_id',
            'team_name',
            'project_title',
            'organization',
        ]
        read_only_fields = ['id']


class TrackSerializer(serializers.ModelSerializer):
    """Serializer for Track model with nested presentations."""

    presentations = PresentationSerializer(many=True, read_only=True)

    class Meta:
        model = Track
        fields = [
            'track_name',
            'room',
            'presentations',
        ]
        read_only_fields = ['id']


class ProgramSerializer(serializers.ModelSerializer):
    """Serializer for Program model with nested tracks."""

    tracks = TrackSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = [
            'program_name',
            'tracks',
        ]
        read_only_fields = ['id']


class TrackWinnerSerializer(serializers.ModelSerializer):
    """Serializer for TrackWinner model."""

    class Meta:
        model = TrackWinner
        fields = [
            'track_name',
            'winner_name',
        ]
        read_only_fields = ['id']


class SpecialAwardSerializer(serializers.ModelSerializer):
    """Serializer for SpecialAward model."""

    class Meta:
        model = SpecialAward
        fields = [
            'program_name',
            'award_winner',
        ]
        read_only_fields = ['id']


# ==================== Event Serializers ====================

class EventReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for frontend consumption."""

    programs = ProgramSerializer(many=True, read_only=True)
    track_winners = TrackWinnerSerializer(many=True, read_only=True)
    special_awards = SpecialAwardSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            'event_uuid',
            'event_name',
            'event_date',
            'event_time',
            'upper_bullet_points',
            'lower_bullet_points',
            'is_published',
            'programs',
            'track_winners',
            'special_awards',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['event_uuid', 'created_at', 'updated_at']


# ==================== Sync Serializers (for Google Sheets POST) ====================

class PresentationSyncSerializer(serializers.Serializer):
    """
    Serializer for presentation data from Google Sheets.
    
    Handles both regular presentations and 'Break' entries.
    For Breaks (identified by project_title containing 'Break'), 
    team_id and team_name are optional.
    """

    order = serializers.IntegerField(min_value=1)
    team_id = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    team_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    project_title = serializers.CharField(max_length=500)
    organization = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        """
        Validate presentation data.
        For 'Break' entries, relax requirements for team_id and team_name.
        For regular presentations, ensure team_name is provided.
        """
        project_title = attrs.get('project_title', '').strip().lower()
        is_break = 'break' in project_title or (attrs.get('organization', '').strip().lower() == 'break')
        
        # Order is always required
        if 'order' not in attrs:
            raise serializers.ValidationError({'order': 'This field is required.'})
        
        # For breaks, team_name and team_id are optional
        if is_break:
            return attrs
        
        # For regular presentations, team_name is required
        team_name = attrs.get('team_name', '').strip() if attrs.get('team_name') else ''
        if not team_name:
            raise serializers.ValidationError({
                'team_name': 'This field is required for non-break presentations.'
            })
        
        return attrs


class TrackSyncSerializer(serializers.Serializer):
    """Serializer for track data from Google Sheets."""

    track_name = serializers.CharField(max_length=255)
    room = serializers.CharField(max_length=255)
    presentations = PresentationSyncSerializer(many=True)


class ProgramSyncSerializer(serializers.Serializer):
    """Serializer for program data from Google Sheets."""

    program_name = serializers.CharField(max_length=255)
    tracks = TrackSyncSerializer(many=True)


class TrackWinnerSyncSerializer(serializers.Serializer):
    """Serializer for track winner data from Google Sheets."""

    track_name = serializers.CharField(max_length=255)
    winner_name = serializers.CharField(max_length=255)


class SpecialAwardSyncSerializer(serializers.Serializer):
    """Serializer for special award data from Google Sheets."""

    program_name = serializers.CharField(max_length=255)
    award_winner = serializers.CharField(max_length=255)


class BasicInfoSerializer(serializers.Serializer):
    """Serializer for basic_info section from Google Sheets."""

    event_name = serializers.CharField(max_length=255)
    event_date = serializers.DateField()
    event_time = serializers.TimeField()
    upper_bullet_points = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        required=False
    )
    lower_bullet_points = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        required=False
    )


class WinnersSerializer(serializers.Serializer):
    """Serializer for winners section from Google Sheets."""

    track_winners = TrackWinnerSyncSerializer(many=True, required=False)
    special_awards = SpecialAwardSyncSerializer(many=True, required=False)


class EventSyncSerializer(serializers.Serializer):
    """
    Main serializer for Google Sheets sync endpoint.

    Accepts the full JSON payload matching the specification:
    {
        "basic_info": {...},
        "schedule": [...],
        "winners": {...}
    }
    """

    basic_info = BasicInfoSerializer(required=False)
    schedule = ProgramSyncSerializer(many=True, required=False)
    winners = WinnersSerializer(required=False)

    def validate(self, attrs):
        """Ensure at least one section is provided."""
        if not any(key in attrs for key in ['basic_info', 'schedule', 'winners']):
            raise serializers.ValidationError(
                "At least one of 'basic_info', 'schedule', or 'winners' must be provided."
            )
        return attrs

