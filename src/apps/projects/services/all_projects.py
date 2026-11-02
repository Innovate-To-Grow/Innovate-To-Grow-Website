"""/projects/all/'s current part: the active schedule's projects that the archive does not hold yet, as list rows.

The list is that part (in team_ordering()) followed by the archive (in archive_ordering()). A current team that is
already archived is listed once, as its archive row, matched as /projects/<id>/ matches it
(apps.projects.services.current_project_links); that row names the CurrentProject it stands in for.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from apps.projects.services.catalog_filters import current_matches
from apps.projects.services.current_project_links import CurrentProjectLink, active_current_project_links

# The compact archive row's fields (CompactPastProjectSerializer), in its order: the abstract stays on the detail.
_COMPACT_ROW_FIELDS = (
    "id",
    "semester_label",
    "class_code",
    "team_number",
    "team_name",
    "project_title",
    "organization",
    "industry",
    "student_names",
    "track",
    "presentation_order",
)


@dataclass(frozen=True)
class CurrentCatalog:
    # The active schedule's projects that are not archived and pass the params, as list rows in team_ordering().
    rows: list[dict]
    # The CurrentProject id each archived team's archive row stands in for, by archive project id.
    current_ids_by_archive_id: dict[uuid.UUID, str]


def compact_current_row(link: CurrentProjectLink) -> dict:
    """A current project as a /projects/all/ row: the compact archive row's fields, then its catalog fields."""
    return {
        **{name: link.detail[name] for name in _COMPACT_ROW_FIELDS},
        "catalog": "current",
        "is_presenting": link.is_presenting,
        "current_project_id": None,
    }


def current_catalog(params: Mapping) -> CurrentCatalog:
    """The active schedule's part of /projects/all/ for the validated PastProjectQuerySerializer params.

    A team's text and term are its CurrentProject's; one the schedule only lists has the schedule's term. An
    archived team is left to its archive row, which the archive's own filters keep or drop.
    """
    rows = []
    current_ids_by_archive_id = {}
    for link in active_current_project_links():
        if link.archived is not None:
            current_ids_by_archive_id.setdefault(link.archived.pk, link.detail["id"])
        elif current_matches(link.detail, link.detail["semester_label"], params):
            rows.append(compact_current_row(link))
    return CurrentCatalog(rows=rows, current_ids_by_archive_id=current_ids_by_archive_id)
