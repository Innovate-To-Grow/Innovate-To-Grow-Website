"""
Sync serializers for Google Sheets POST endpoint.
"""

from rest_framework import serializers


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
        project_title = attrs.get("project_title", "").strip().lower()
        is_break = "break" in project_title or (attrs.get("organization", "").strip().lower() == "break")

        # Order is always required
        if "order" not in attrs:
            raise serializers.ValidationError({"order": "This field is required."})

        # For breaks, team_name and team_id are optional
        if is_break:
            return attrs

        # For regular presentations, team_name is required
        team_name = attrs.get("team_name", "").strip() if attrs.get("team_name") else ""
        if not team_name:
            raise serializers.ValidationError({"team_name": "This field is required for non-break presentations."})

        return attrs


class TrackSyncSerializer(serializers.Serializer):
    """Serializer for track data from Google Sheets."""

    track_name = serializers.CharField(max_length=255)
    room = serializers.CharField(max_length=255)
    start_time = serializers.TimeField(required=False, allow_null=True)
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


class ExpoRowSerializer(serializers.Serializer):
    """Serializer for expo table row from Google Sheets."""

    time = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    room = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        """Validate that at least time and description are provided (room can be in header row)."""
        # Skip rows that are completely empty
        if not any(attrs.values()):
            return attrs
        # If any field is provided, ensure time and description are present
        if attrs.get("time") or attrs.get("description"):
            if not attrs.get("time"):
                raise serializers.ValidationError({"time": "Time is required when description is provided."})
            if not attrs.get("description"):
                raise serializers.ValidationError({"description": "Description is required when time is provided."})
        return attrs


class ReceptionRowSerializer(serializers.Serializer):
    """Serializer for reception table row from Google Sheets."""

    time = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    room = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        """Validate that at least time and description are provided (room can be in header row)."""
        # Skip rows that are completely empty
        if not any(attrs.values()):
            return attrs
        # If any field is provided, ensure time and description are present
        if attrs.get("time") or attrs.get("description"):
            if not attrs.get("time"):
                raise serializers.ValidationError({"time": "Time is required when description is provided."})
            if not attrs.get("description"):
                raise serializers.ValidationError({"description": "Description is required when time is provided."})
        return attrs


class BasicInfoSerializer(serializers.Serializer):
    """Serializer for basic_info section from Google Sheets."""

    event_name = serializers.CharField(max_length=255)
    event_date = serializers.DateField()
    event_time = serializers.TimeField()
    upper_bullet_points = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)
    lower_bullet_points = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)


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
        "expo_table": [...],
        "reception_table": [...],
        "winners": {...}
    }
    """

    basic_info = BasicInfoSerializer(required=False)
    schedule = ProgramSyncSerializer(many=True, required=False)
    expo_table = ExpoRowSerializer(many=True, required=False)
    reception_table = ReceptionRowSerializer(many=True, required=False)
    winners = WinnersSerializer(required=False)

    def validate(self, attrs):
        """Ensure at least one section is provided."""
        if not any(key in attrs for key in ["basic_info", "schedule", "expo_table", "reception_table", "winners"]):
            raise serializers.ValidationError(
                "At least one of 'basic_info', 'schedule', 'expo_table', 'reception_table', or 'winners' must be provided."
            )
        return attrs
