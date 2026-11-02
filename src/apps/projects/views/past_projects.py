from django.db.models import Prefetch
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from ..models import Project, Semester
from ..ordering import team_ordering
from ..pagination import PastProjectsPageNumberPagination
from ..serializers import PastSemesterPageQuerySerializer, SemesterWithProjectsSerializer


class PastProjectsAPIView(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = SemesterWithProjectsSerializer
    pagination_class = PastProjectsPageNumberPagination

    # noinspection PyMethodMayBeStatic
    def get_queryset(self):
        # Every published semester is a past semester (all are imported + published by the sheet
        # sync), so the newest published semester is included rather than hidden as "current".
        return Semester.objects.filter(is_published=True).prefetch_related(
            Prefetch("projects", queryset=Project.objects.order_by(*team_ordering()))
        )

    def list(self, request, *args, **kwargs):
        # Reject a malformed page or page size with a 400 field error, as /projects/archive/ does, instead of
        # the paginator's 404 for a bad page and its silent fallback (echoed into the next link) for a bad size.
        PastSemesterPageQuerySerializer(data=request.query_params).is_valid(raise_exception=True)
        return super().list(request, *args, **kwargs)
