"""
Serializers for Past Projects API endpoints.
"""

from rest_framework import serializers
from ..models.past_projects import SharedProjectURL


class PastProjectSerializer(serializers.Serializer):
    """
    Serializer for past project data from Google Sheets.
    
    This is a read-only serializer that validates the structure
    of project data returned from Google Sheets.
    """
    
    Year_Semester = serializers.CharField(required=False, allow_blank=True)
    Class = serializers.CharField(required=False, allow_blank=True)
    Team = serializers.CharField(required=False, allow_blank=True)  # Team#
    Team_Name = serializers.CharField(required=False, allow_blank=True)
    Project_Title = serializers.CharField(required=False, allow_blank=True)
    Organization = serializers.CharField(required=False, allow_blank=True)
    Industry = serializers.CharField(required=False, allow_blank=True)
    Abstract = serializers.CharField(required=False, allow_blank=True)
    Student_Names = serializers.CharField(required=False, allow_blank=True)

    def to_representation(self, instance):
        """
        Transform the data to match frontend expectations.
        
        The Google Sheets service returns data with keys like "Year-Semester",
        but we need to handle both formats.
        """
        # If instance is already a dict with the right keys, return as-is
        if isinstance(instance, dict):
            # Map keys to match frontend expectations
            return {
                "Year-Semester": instance.get("Year-Semester", ""),
                "Class": instance.get("Class", ""),
                "Team#": instance.get("Team#", ""),
                "Team Name": instance.get("Team Name", ""),
                "Project Title": instance.get("Project Title", ""),
                "Organization": instance.get("Organization", ""),
                "Industry": instance.get("Industry", ""),
                "Abstract": instance.get("Abstract", ""),
                "Student Names": instance.get("Student Names", ""),
            }
        return super().to_representation(instance)


class SharedProjectURLCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a shared project URL.
    
    Validates the request payload for creating a shared URL.
    """
    
    team_names = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False,
        help_text="List of team names to filter projects."
    )
    
    team_numbers = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False,
        help_text="List of team numbers to filter projects."
    )
    
    project_keys = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="List of unique project keys for precise matching."
    )

    def validate(self, attrs):
        """Validate that at least one team name or number is provided."""
        team_names = attrs.get('team_names', [])
        team_numbers = attrs.get('team_numbers', [])
        
        if not team_names and not team_numbers:
            raise serializers.ValidationError(
                "At least one team name or team number must be provided."
            )
        
        return attrs


class SharedProjectURLRetrieveSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving a shared project URL.
    
    Returns the UUID, team names, and team numbers.
    """
    
    class Meta:
        model = SharedProjectURL
        fields = ['uuid', 'team_names', 'team_numbers', 'project_keys', 'created_at', 'expires_at']
        read_only_fields = ['uuid', 'created_at', 'expires_at']

