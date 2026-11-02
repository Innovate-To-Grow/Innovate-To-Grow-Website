"""The projects an AI search offers the model for a query, and the projects its reply names.

Two scopes: "past" searches the published archive, as /projects/past-all/ lists it; "all" searches what
/projects/all/ lists, the active schedule's projects that the archive does not hold yet and then the archive. A
current team the archive already holds is offered once, as its archive project.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Iterable
from dataclasses import dataclass, fields
from functools import reduce

from django.db.models import Q, QuerySet

from apps.projects.models import Project
from apps.projects.ordering import archive_ordering
from apps.projects.services.catalog_filters import SEARCH_FIELDS, current_matches
from apps.projects.services.current_project_links import (
    CurrentProjectLink,
    active_current_project_links,
    resolve_current_project_links,
)

SCOPE_PAST = "past"
SCOPE_ALL = "all"
AI_SEARCH_SCOPES = (SCOPE_PAST, SCOPE_ALL)

CANDIDATE_LIMIT = 80
# With the "all" scope, at most this many candidates are current projects: they come first, and the archive fills
# the rest, so the prompt stays about the size it is for "past".
CURRENT_CANDIDATE_LIMIT = 20

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.&/-]*", re.IGNORECASE)
_STOP_WORDS = {
    "a",
    "about",
    "and",
    "are",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "past",
    "project",
    "projects",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class AISearchCandidate:
    """A project as a candidate line of the prompt describes it: an archive project or a current one."""

    id: str
    project_title: str
    semester_label: str
    class_code: str
    team_number: str
    team_name: str
    organization: str
    industry: str
    abstract: str

    @classmethod
    def from_project(cls, project: Project) -> AISearchCandidate:
        return cls(
            id=str(project.pk),
            project_title=project.project_title,
            semester_label=project.semester.label,
            class_code=project.class_code,
            team_number=project.team_number,
            team_name=project.team_name,
            organization=project.organization,
            industry=project.industry,
            abstract=project.abstract,
        )

    @classmethod
    def from_link(cls, link: CurrentProjectLink) -> AISearchCandidate:
        # The detail names its fields as the archive does; its semester_label is the schedule's term.
        return cls(**{field.name: link.detail[field.name] for field in fields(cls)})


def past_project_ai_queryset() -> QuerySet[Project]:
    """Published past projects, matching /projects/past-all/ semantics (every published semester,
    including the newest — it is a real past term imported by the sheet sync)."""
    return Project.objects.filter(semester__is_published=True).select_related("semester").order_by(*archive_ordering())


def _tokens(query: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(query.lower()):
        token = match.strip("-/.&")
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _candidate_filter(tokens: Iterable[str]) -> Q:
    """Any of the tokens in any field a search reads."""
    return reduce(operator.or_, (Q(**{f"{name}__icontains": token}) for token in tokens for name in SEARCH_FIELDS))


def _current_candidates(tokens: list[str], limit: int) -> list[AISearchCandidate]:
    """Up to ``limit`` of the active schedule's projects that the archive does not hold yet and whose text holds one of
    ``tokens``, in team_ordering()."""
    candidates = []
    for link in active_current_project_links():
        if len(candidates) >= limit:
            break
        term = link.detail["semester_label"]
        if link.archived is None and any(current_matches(link.detail, term, {"search": token}) for token in tokens):
            candidates.append(AISearchCandidate.from_link(link))
    return candidates


def find_ai_search_candidates(
    query: str, *, scope: str = SCOPE_PAST, candidate_limit: int = CANDIDATE_LIMIT
) -> list[AISearchCandidate]:
    """The projects whose text holds a word of ``query``, at most ``candidate_limit``: archive projects newest first,
    after (with the "all" scope) up to CURRENT_CANDIDATE_LIMIT current ones."""
    tokens = _tokens(query)
    if not tokens:
        return []
    current = _current_candidates(tokens, min(CURRENT_CANDIDATE_LIMIT, candidate_limit)) if scope == SCOPE_ALL else []
    archive = past_project_ai_queryset().filter(_candidate_filter(tokens)).distinct()[: candidate_limit - len(current)]
    return current + [AISearchCandidate.from_project(project) for project in archive]


def _result_id(result: Project | CurrentProjectLink) -> str:
    return str(result.pk) if isinstance(result, Project) else result.detail["id"]


def ai_search_results(project_ids: list[str], *, scope: str) -> list[Project | CurrentProjectLink]:
    """The projects ``project_ids`` (canonical UUIDs, in the model's order) name, in that order and each once.

    Published archive projects; with the "all" scope also current projects, of any schedule, one the archive has
    imported since as its archive project. An id that names neither is dropped.
    """
    archive = {str(project.pk): project for project in past_project_ai_queryset().filter(id__in=project_ids)}
    links = resolve_current_project_links(set(project_ids) - archive.keys()) if scope == SCOPE_ALL else {}
    results = {}
    for project_id in project_ids:
        result = archive.get(project_id) or links.get(project_id)
        if isinstance(result, CurrentProjectLink) and result.archived is not None:
            result = result.archived
        if result is not None:
            results.setdefault(_result_id(result), result)
    return list(results.values())
