from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CurrentProjectSchedule
from event.serializers import CurrentProjectSerializer


class CurrentProjectsAPIView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def get(self, request):
        cache_key = "event:current-projects"
        cached = cache.get(cache_key)
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
        cache.set(cache_key, data, timeout=300)
        return Response(data)
