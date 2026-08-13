from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.http_cache import public_json_response

from ..models import Project
from ..serializers import CompactPastProjectSerializer, PastProjectQuerySerializer


class CompactPastProjectsPagination(PageNumberPagination):
    page_size = 20


class CompactPastProjectsAPIView(APIView):
    """Paginated, filterable project-level archive discovery endpoint."""

    permission_classes = [AllowAny]

    def get(self, request):
        query_serializer = PastProjectQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        queryset = Project.objects.filter(semester__is_published=True).select_related("semester")
        if search := params.get("search"):
            queryset = queryset.filter(
                Q(project_title__icontains=search)
                | Q(team_name__icontains=search)
                | Q(team_number__icontains=search)
                | Q(organization__icontains=search)
                | Q(industry__icontains=search)
                | Q(class_code__icontains=search)
                | Q(abstract__icontains=search)
                | Q(student_names__icontains=search)
            )
        if year := params.get("year"):
            queryset = queryset.filter(semester__year=year)
        if season := params.get("season"):
            queryset = queryset.filter(semester__season=season)
        if semester := params.get("semester"):
            queryset = queryset.filter(semester__label__iexact=semester)

        queryset = queryset.order_by(
            "-semester__year",
            "-semester__season",
            "class_code",
            "team_number",
            "id",
        )
        paginator = CompactPastProjectsPagination()
        paginator.page_size = params["page_size"]
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CompactPastProjectSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        return public_json_response(request, response.data)
