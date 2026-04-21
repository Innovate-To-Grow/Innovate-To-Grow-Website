from rest_framework import serializers

from event.models import CurrentProject


class CurrentProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrentProject
        fields = [
            "id",
            "class_code",
            "team_number",
            "team_name",
            "project_title",
            "organization",
            "industry",
            "abstract",
            "student_names",
            "is_presenting",
        ]
