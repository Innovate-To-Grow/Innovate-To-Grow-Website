from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event.models import CurrentProjectSchedule
from apps.event.serializers import CurrentProjectSerializer
from apps.event.services.current_projects import CURRENT_PROJECTS_CACHE_KEY


class CurrentProjectsAPIView(APIView):
    rate_limit_scope = "public-read"
    permission_classes = [AllowAny]
    authentication_classes = []

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def get(self, request):
        cached = cache.get(CURRENT_PROJECTS_CACHE_KEY)
        if cached is not None:
            return Response(cached)

        config = CurrentProjectSchedule.load()
        if not config:
            return Response({"detail": "No published projects found."}, status=404)

        projects = config.projects.order_by("class_code", "team_number")
        data = {
            "schedule": {"id": str(config.pk), "name": config.name},
            "projects": CurrentProjectSerializer(projects, many=True).data,
        }
        cache.set(CURRENT_PROJECTS_CACHE_KEY, data, timeout=300)
        return Response(data)
