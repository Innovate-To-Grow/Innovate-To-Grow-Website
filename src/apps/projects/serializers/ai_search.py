from rest_framework import serializers

from ..services.ai_search_candidates import AI_SEARCH_SCOPES, SCOPE_PAST
from ..services.current_project_links import CurrentProjectLink
from .project import ProjectTableSerializer, _ArchiveCatalogFields


class PastProjectAISearchSerializer(serializers.Serializer):
    query = serializers.CharField(allow_blank=True, trim_whitespace=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=10, default=10)
    # What the search ranks: "past", the published archive (Past Projects), or "all", what /projects/all/ lists.
    scope = serializers.ChoiceField(choices=AI_SEARCH_SCOPES, required=False, default=SCOPE_PAST)

    def __init__(self, *args, max_query_chars: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_query_chars = max_query_chars

    def validate_query(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Query must not be blank.")
        cap = self._max_query_chars
        if cap is not None and cap > 0 and len(value) > cap:
            raise serializers.ValidationError(f"Query must be at most {cap} characters.")
        return value


class PastProjectAISearchResultSerializer(_ArchiveCatalogFields, ProjectTableSerializer):
    """An AI search result: a project table row with its catalog fields, as /projects/all/ rows carry them.

    It serializes what apps.projects.services.ai_search_candidates.ai_search_results returns: an archive project, or
    a current project (a CurrentProjectLink), whose detail already holds every field, catalog "current" included.
    """

    class Meta(ProjectTableSerializer.Meta):
        fields = [*ProjectTableSerializer.Meta.fields, "catalog", "is_presenting"]

    def to_representation(self, instance):
        if isinstance(instance, CurrentProjectLink):
            return {name: instance.detail[name] for name in self.Meta.fields}
        return super().to_representation(instance)
