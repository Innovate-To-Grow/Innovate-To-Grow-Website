from django.core.cache import cache
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import Project, Semester
from ..serializers import ProjectTableSerializer


class AllPastProjectsAPIView(ListAPIView):
    """Flat list of all projects from published past semesters (excludes current)."""

    permission_classes = [AllowAny]
    serializer_class = ProjectTableSerializer
    pagination_class = None

    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        newest_pk = Semester.objects.filter(is_published=True).values("pk")[:1]
        return (
            Project.objects.filter(semester__is_published=True)
            .exclude(semester__pk__in=newest_pk)
            .select_related("semester")
            .order_by("-semester__year", "-semester__season", "class_code", "team_number")
        )

    def list(self, request, *args, **kwargs):
        cache_key = "projects:past-all"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=600)
        return response
