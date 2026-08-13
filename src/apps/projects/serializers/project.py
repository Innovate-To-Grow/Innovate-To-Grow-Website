from rest_framework import serializers

from ..models import Project


class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "project_title", "team_name", "organization", "industry", "class_code"]


class CompactPastProjectSerializer(serializers.ModelSerializer):
    """Compact project representation for archive discovery lists."""

    semester_label = serializers.CharField(source="semester.label", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "semester_label",
            "class_code",
            "team_number",
            "team_name",
            "project_title",
            "organization",
            "industry",
            "track",
            "presentation_order",
        ]


class PastProjectQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200, trim_whitespace=True)
    year = serializers.IntegerField(required=False, min_value=2000, max_value=2100)
    season = serializers.ChoiceField(required=False, choices=(1, 2))
    semester = serializers.CharField(required=False, allow_blank=False, max_length=50, trim_whitespace=True)

    def validate(self, attrs):
        if "semester" in self.initial_data and not self.initial_data.get("semester", "").strip():
            raise serializers.ValidationError({"semester": "This field may not be blank."})
        return attrs


class ProjectTableSerializer(serializers.ModelSerializer):
    """Serializer with all fields needed for project data tables."""

    semester_label = serializers.CharField(source="semester.label", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "semester_label",
            "class_code",
            "team_number",
            "team_name",
            "project_title",
            "organization",
            "industry",
            "abstract",
            "student_names",
            "track",
            "presentation_order",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    semester_label = serializers.CharField(source="semester.label", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "project_title",
            "team_name",
            "team_number",
            "organization",
            "industry",
            "abstract",
            "student_names",
            "class_code",
            "track",
            "presentation_order",
            "semester_label",
        ]
