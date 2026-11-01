from rest_framework import serializers

from ..models import Project
from ..pagination import PastProjectsPageNumberPagination


class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "project_title", "team_name", "organization", "industry", "class_code"]


class CompactPastProjectSerializer(serializers.ModelSerializer):
    """Compact project representation for archive discovery lists.

    Abstracts stay on the detail endpoint to keep the list small; student names are short and are included so a
    list can be searched by team member.
    """

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
            "student_names",
            "track",
            "presentation_order",
        ]


class _ArchiveCatalogFields(serializers.Serializer):
    """What /projects/all/ rows and project details add for an archive project: it names its catalog, and only a
    current project has a presenting flag."""

    catalog = serializers.SerializerMethodField()
    is_presenting = serializers.SerializerMethodField()

    def get_catalog(self, project) -> str:
        return "archive"

    def get_is_presenting(self, project) -> None:
        return None


class AllProjectsArchiveRowSerializer(_ArchiveCatalogFields, CompactPastProjectSerializer):
    """An archive row of /projects/all/: the compact row, its catalog, and the current project it stands in for.

    The view passes ``current_ids_by_archive_id`` in the context (apps.projects.services.all_projects.CurrentCatalog).
    """

    current_project_id = serializers.SerializerMethodField()

    class Meta(CompactPastProjectSerializer.Meta):
        fields = [*CompactPastProjectSerializer.Meta.fields, "catalog", "is_presenting", "current_project_id"]

    def get_current_project_id(self, project) -> str | None:
        return self.context.get("current_ids_by_archive_id", {}).get(project.pk)


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


class PastSemesterPageQuerySerializer(serializers.Serializer):
    """Query parameters of the semester-grouped /projects/past/ list, validated like /projects/archive/'s."""

    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=PastProjectsPageNumberPagination.max_page_size,
        default=PastProjectsPageNumberPagination.page_size,
    )


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


class ProjectDetailSerializer(_ArchiveCatalogFields, serializers.ModelSerializer):
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
            "catalog",
            "is_presenting",
        ]
