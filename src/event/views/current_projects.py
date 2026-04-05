from django.core.cache import cache
from django.db.models import Prefetch
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Project, Semester
from projects.serializers import SemesterWithFullProjectsSerializer


class CurrentProjectsAPIView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def get(self, request):
        cache_key = "event:current-projects"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        semester = (
            Semester.objects.filter(is_published=True)
            .prefetch_related(Prefetch("projects", queryset=Project.objects.order_by("class_code", "team_number")))
            .first()
        )

        if semester is None:
            return Response({"detail": "No published projects found."}, status=404)

        data = SemesterWithFullProjectsSerializer(semester).data
        cache.set(cache_key, data, timeout=300)
        return Response(data)
