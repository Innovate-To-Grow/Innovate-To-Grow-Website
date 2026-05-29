from rest_framework import serializers

from ..models import Semester
from .project import ProjectListSerializer, ProjectTableSerializer


class SemesterWithProjectsSerializer(serializers.ModelSerializer):
    projects = ProjectListSerializer(many=True, read_only=True)

    class Meta:
        model = Semester
        fields = ["id", "year", "season", "label", "projects"]


class SemesterWithFullProjectsSerializer(serializers.ModelSerializer):
    projects = ProjectTableSerializer(many=True, read_only=True)

    class Meta:
        model = Semester
        fields = ["id", "year", "season", "label", "projects"]
