from collections.abc import Callable

from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination


class PastProjectsPageNumberPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 20


class CompactPastProjectsPagination(PageNumberPagination):
    # The views set page_size from their validated params.
    page_size = 20


class ChainedRows:
    """Rows already in hand followed by a queryset's, paged as one list (/projects/all/'s current head, then the archive).

    Django's Paginator only counts and slices what it pages, so DRF's paginators keep their 404 for a page past the
    end and their next/previous links across the boundary. The tail is counted in the database and only the part of
    it a page shows is read, through ``serialize``.
    """

    def __init__(self, head: list[dict], tail: QuerySet, serialize: Callable[[QuerySet], list]):
        self.head = head
        self.tail = tail
        self.serialize = serialize

    def count(self) -> int:
        return len(self.head) + self.tail.count()

    def __getitem__(self, window: slice) -> list:
        # The paginator slices [bottom:top], neither bound negative; an open end reads the rest of the tail.
        start, stop = window.start or 0, window.stop
        rows = self.head[start:stop]
        tail_start = max(start - len(self.head), 0)
        tail_stop = None if stop is None else max(stop - len(self.head), 0)
        if tail_stop is None or tail_stop > tail_start:
            rows = [*rows, *self.serialize(self.tail[tail_start:tail_stop])]
        return rows
