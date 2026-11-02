"""The search and term filters of the project lists, for archive projects and for current-semester ones alike.

/projects/archive/ and /projects/all/ take the same params (PastProjectQuerySerializer): an archive project is
filtered in the database, a current project (apps.projects.services.all_projects) in Python, the same way.
"""

from __future__ import annotations

import operator
import re
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

# A term as Semester.label spells it: "2026-2 Fall" is year 2026, season 2.
_TERM_RE = re.compile(r"^(\d{4})-(\d)\s")


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


def _text_matches(fields: Mapping, search: str) -> bool:
    needle = search.casefold()
    return any(needle in fields.get(name, "").casefold() for name in SEARCH_FIELDS)


def _term_matches(term: str, params: Mapping) -> bool:
    match = _TERM_RE.match(term)
    year, season = (int(match.group(1)), int(match.group(2))) if match else (None, None)
    if params.get("year") and params["year"] != year:
        return False
    if params.get("season") and params["season"] != season:
        return False
    return not params.get("semester") or params["semester"].casefold() == term.casefold()


def current_matches(fields: Mapping, term: str, params: Mapping) -> bool:
    """Whether a current project passes the validated params as an archive project with its text and term would.

    ``fields`` holds its SEARCH_FIELDS text, ``term`` its Year-Semester ("2026-2 Fall"). The search is a substring
    of any field, ignoring case; year and season are read from the term, and the semester is the whole term.
    """
    if (search := params.get("search")) and not _text_matches(fields, search):
        return False
    return _term_matches(term, params)
