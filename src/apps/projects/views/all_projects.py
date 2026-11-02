from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.http_cache import public_json_response

from ..pagination import ChainedRows, CompactPastProjectsPagination
from ..serializers import AllProjectsArchiveRowSerializer, PastProjectQuerySerializer
from ..services.all_projects import current_catalog
from ..services.catalog_filters import archive_queryset


class AllProjectsAPIView(APIView):
    """Every project: the active schedule's that are not archived yet, then the archive, paged and filtered as one list.

    No server cache: the ETag comes from the content, so a schedule sync or an archive import shows on the next
    uncached request.
    """

    # A paged list (the All Projects page requests about ten pages at once), not a whole-catalog response.
    rate_limit_scope = "public-read"

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        query_serializer = PastProjectQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        current = current_catalog(params)
        context = {"current_ids_by_archive_id": current.current_ids_by_archive_id}
        rows = ChainedRows(
            current.rows,
            archive_queryset(params),
            lambda projects: AllProjectsArchiveRowSerializer(projects, many=True, context=context).data,
        )
        paginator = CompactPastProjectsPagination()
        paginator.page_size = params["page_size"]
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response(page)
        return public_json_response(request, response.data)
