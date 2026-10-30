from django.http import Http404
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import Project
from ..serializers import ProjectDetailSerializer
from ..services.current_project_links import resolve_current_project_link


class ProjectDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ProjectDetailSerializer
    queryset = Project.objects.filter(semester__is_published=True).select_related("semester")
    lookup_field = "pk"

    def retrieve(self, request, *args, **kwargs):
        try:
            return super().retrieve(request, *args, **kwargs)
        except Http404:
            # Not an archive id: it may be a current-semester project link from an earlier schedule.
            link = resolve_current_project_link(kwargs[self.lookup_field])
            if link is None:
                raise
            if link.archived is not None:
                return Response(self.get_serializer(link.archived).data)
            return Response(link.detail)
