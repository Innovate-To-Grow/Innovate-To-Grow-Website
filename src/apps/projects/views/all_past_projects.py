from django.core.cache import cache
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import Project
from ..serializers import ProjectTableSerializer


class AllPastProjectsAPIView(ListAPIView):
    """Flat list of all projects from every published semester.

    Past projects come from the Google Sheet sync, which publishes the semesters it imports, so the
    newest published semester is a real past semester (e.g. the most recently completed term) and is
    included — it is never treated as a hidden "current" semester.
    """

    permission_classes = [AllowAny]
    serializer_class = ProjectTableSerializer
    pagination_class = None

    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        return (
            Project.objects.filter(semester__is_published=True)
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
