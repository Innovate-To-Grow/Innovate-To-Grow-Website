from django.http import Http404
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from apps.core.utils.http_cache import public_json_response

from ..models import Project
from ..serializers import ProjectDetailSerializer
from ..services.current_project_links import resolve_current_project_link


class ProjectDetailAPIView(RetrieveAPIView):
    rate_limit_scope = "public-read"
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ProjectDetailSerializer
    queryset = Project.objects.filter(semester__is_published=True).select_related("semester")
    lookup_field = "pk"

    def retrieve(self, request, *args, **kwargs):
        # Public catalog text, the same for every visitor: cacheable like /projects/archive/.
        return public_json_response(request, self._project_data(kwargs[self.lookup_field]))

    def _project_data(self, project_id) -> dict:
        try:
            return self.get_serializer(self.get_object()).data
        except Http404:
            # Not an archive id: it may be a current-semester project link from an earlier schedule.
            link = resolve_current_project_link(project_id)
            if link is None:
                raise
            if link.archived is not None:
                return self.get_serializer(link.archived).data
            return link.detail
