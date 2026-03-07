from rest_framework import serializers

from ..models import Project


class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "project_title", "team_name", "organization", "industry", "class_code"]


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
