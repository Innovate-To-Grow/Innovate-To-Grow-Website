"""The rows of a shared curation, taken from the published catalog rather than from what a client sent.

A share is a public page on the site, so its rows must say what the catalog says: the archive, or the event for a
current-semester project the archive does not hold yet. On every write each row is rebuilt from the project it
names; a row naming no published project is refused, unless the share already holds it (a project removed from the
archive since, or a deleted CurrentProject), and then it is kept exactly as stored. Reads show the catalog's current
text for every row that still resolves, which also adds the project id to legacy rows saved before rows carried one,
and shows a current row as its archive row once the past-project sheet has imported the team. Rows that name the
same project (a current row and its archive row after that import) are kept once, on writes and on reads.
"""

from __future__ import annotations

from apps.projects.services.shares.matching import ROW_FIELDS, _Catalog, _row_id, _row_stable_key


class UnknownShareRows(Exception):
    """Raised when submitted rows name no published project and are not already in the share."""

    def __init__(self, count: int):
        super().__init__(count)
        self.count = count


def _row_identities(row):
    """How a submitted row is recognised as one the share stores: its id, else its stable key; or its content."""
    if row.get("id"):
        identities = [("id", _row_id(row))]
    else:
        key = _row_stable_key(row)
        identities = [("key", key)] if key is not None else []
    identities.append(("row", tuple(str(row.get(field) or "") for field in ROW_FIELDS)))
    return identities


def _stored_rows_by_identity(stored_rows) -> dict:
    by_identity = {}
    for row in stored_rows:
        for identity in _row_identities(row):
            by_identity.setdefault(identity, row)
    return by_identity


def _unique_rows(rows) -> list[dict]:
    """``rows`` without each row that names a project an earlier row names: once the archive imports a current team,
    a share holding its current row and its archive row (or two of its ids) holds the same project twice."""
    seen = set()
    unique = []
    for row in rows:
        project_id = _row_id(row)
        if project_id is not None and project_id in seen:
            continue
        seen.add(project_id)
        unique.append(row)
    return unique


def rebuild_share_rows(submitted_rows, stored_rows=()) -> list[dict]:
    """The rows to store for ``submitted_rows``: each from the catalog, or as ``stored_rows`` already hold it.

    Raises :class:`UnknownShareRows` when a row names no published project and the share does not hold it.
    """
    catalog = _Catalog(submitted_rows)
    stored = _stored_rows_by_identity(stored_rows)
    rebuilt = []
    unknown = 0
    for row in submitted_rows:
        rebuilt_row = catalog.row_for(row)
        if rebuilt_row is None:
            kept = next((stored[identity] for identity in _row_identities(row) if identity in stored), None)
            rebuilt_row = dict(kept) if kept is not None else None
        if rebuilt_row is None:
            unknown += 1
        else:
            rebuilt.append(rebuilt_row)
    if unknown:
        raise UnknownShareRows(unknown)
    return _unique_rows(rebuilt)


def rows_for_display(stored_rows) -> list[dict]:
    """The stored rows with the catalog's current text wherever a row still names a published project.

    Rows saved before rows carried an id resolve by Year-Semester + Class + Team#; a row that no longer resolves
    is shown as stored. The stored snapshot itself is not changed.
    """
    catalog = _Catalog(stored_rows)
    return _unique_rows([catalog.row_for(row) or dict(row) for row in stored_rows])
