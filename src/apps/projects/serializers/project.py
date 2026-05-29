from rest_framework import serializers

from ..models import Project


class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "project_title", "team_name", "organization", "industry", "class_code"]


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
