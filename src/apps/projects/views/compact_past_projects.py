from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.http_cache import public_json_response

from ..pagination import CompactPastProjectsPagination
from ..serializers import CompactPastProjectSerializer, PastProjectQuerySerializer
from ..services.catalog_filters import archive_queryset


class CompactPastProjectsAPIView(APIView):
    """Paginated, filterable project-level archive discovery endpoint."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        query_serializer = PastProjectQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        paginator = CompactPastProjectsPagination()
        paginator.page_size = params["page_size"]
        page = paginator.paginate_queryset(archive_queryset(params), request, view=self)
        serializer = CompactPastProjectSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        return public_json_response(request, response.data)
