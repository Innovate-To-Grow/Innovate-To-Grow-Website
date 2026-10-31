from rest_framework.pagination import PageNumberPagination


class PastProjectsPageNumberPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 20


class CompactPastProjectsPagination(PageNumberPagination):
    # The views set page_size from their validated params.
    page_size = 20
