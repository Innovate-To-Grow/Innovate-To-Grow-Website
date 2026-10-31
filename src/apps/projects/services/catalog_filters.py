"""The search and term filters of the project lists, validated by PastProjectQuerySerializer."""

from __future__ import annotations

import operator
from collections.abc import Mapping
from functools import reduce

from django.db.models import Q, QuerySet

from apps.projects.models import Project
from apps.projects.ordering import archive_ordering

# What a search reads. List rows leave the abstract out, but it is searched all the same.
SEARCH_FIELDS = (
    "project_title",
    "team_name",
    "team_number",
    "organization",
    "industry",
    "class_code",
    "abstract",
    "student_names",
)


def _search_q(search: str) -> Q:
    return reduce(operator.or_, (Q(**{f"{name}__icontains": search}) for name in SEARCH_FIELDS))


def archive_queryset(params: Mapping) -> QuerySet[Project]:
    """The published archive projects that pass the validated params, in archive_ordering() (the id breaks ties)."""
    queryset = Project.objects.filter(semester__is_published=True).select_related("semester")
    if search := params.get("search"):
        queryset = queryset.filter(_search_q(search))
    if year := params.get("year"):
        queryset = queryset.filter(semester__year=year)
    if season := params.get("season"):
        queryset = queryset.filter(semester__season=season)
    if semester := params.get("semester"):
        queryset = queryset.filter(semester__label__iexact=semester)
    return queryset.order_by(*archive_ordering(), "id")
