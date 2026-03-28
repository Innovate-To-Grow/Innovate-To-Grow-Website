from django.core.cache import cache
from django.db.models import Prefetch
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Project, Semester
from ..serializers import SemesterWithFullProjectsSerializer


class CurrentProjectsAPIView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def get(self, request):
        cache_key = "projects:current"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        semester = (
            Semester.objects.filter(is_published=True, is_current=True)
            .prefetch_related(Prefetch("projects", queryset=Project.objects.order_by("class_code", "team_number")))
            .first()
        )

        # Fallback: if no explicit current semester, use newest published
        if semester is None:
            semester = (
                Semester.objects.filter(is_published=True)
                .prefetch_related(Prefetch("projects", queryset=Project.objects.order_by("class_code", "team_number")))
                .first()
            )

        if not semester:
            return Response({"detail": "No published projects found."}, status=404)

        data = SemesterWithFullProjectsSerializer(semester).data
        cache.set(cache_key, data, timeout=300)
        return Response(data)
