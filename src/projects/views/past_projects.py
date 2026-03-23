from django.db.models import Prefetch
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from ..models import Project, Semester
from ..pagination import PastProjectsPageNumberPagination
from ..serializers import SemesterWithProjectsSerializer


class PastProjectsAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SemesterWithProjectsSerializer
    pagination_class = PastProjectsPageNumberPagination

    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        current_pk_qs = Semester.objects.filter(is_published=True).values("pk")[:1]

        return (
            Semester.objects.filter(is_published=True)
            .exclude(pk__in=current_pk_qs)
            .prefetch_related(Prefetch("projects", queryset=Project.objects.order_by("class_code", "team_number")))
        )
