"""
CSV import service for past projects.

Parses CSV files exported from the legacy "Project Resources" Google Sheet
and creates Semester + Project records.
"""

import csv
import io
import re
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction

from apps.projects.models import Project, Semester

YEAR_SEMESTER_RE = re.compile(r"^(\d{4})-(\d)\s")

# Map CSV column indices to Project field names.
# Headers 8/9 are non-breaking spaces in the legacy export, so we use indices.
FIELD_INDICES = {
    1: "class_code",
    2: "team_number",
    3: "team_name",
    4: "project_title",
    5: "organization",
    6: "industry",
    8: "abstract",
    9: "student_names",
}


@dataclass
class ImportResult:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_semester(value: str) -> tuple[int, int] | None:
    """Parse a semester label without reading from or mutating the database."""
    match = YEAR_SEMESTER_RE.match(value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


@contextmanager
def _open_csv(csv_file):
    """A text stream over a file path, or over an uploaded/file-like object's content."""
    if isinstance(csv_file, str | bytes):
        with open(csv_file, newline="", encoding="utf-8-sig") as fh:
            yield fh
        return
    # file-like (e.g. Django UploadedFile)
    content = csv_file.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    yield io.StringIO(content)


def _row_fields(row: list[str], line_no: int, result: ImportResult):
    """``(semester_key, fields)`` for an importable row, else None (with an error recorded when it is malformed)."""
    if len(row) < 5:
        return None
    year_sem = row[0].strip()
    if not year_sem:
        return None
    semester_key = _parse_semester(year_sem)
    if semester_key is None:
        result.errors.append(f"Row {line_no}: unparseable Year-Semester '{year_sem}'")
        return None
    fields = {field_name: row[idx].strip() if idx < len(row) else "" for idx, field_name in FIELD_INDICES.items()}
    if not fields.get("project_title"):
        result.errors.append(f"Row {line_no}: missing project_title, skipped")
        return None
    return semester_key, fields


def _already_imported(dup_key: tuple, staged_keys: set) -> bool:
    # Duplicate check: same semester + class_code + team_number, against
    # both already-persisted rows and rows staged earlier in this import.
    year, season, class_code, team_number = dup_key
    return (
        dup_key in staged_keys
        or Project.objects.filter(
            semester__year=year,
            semester__season=season,
            class_code=class_code,
            team_number=team_number,
        ).exists()
    )


def _save_rows(parsed_rows, semesters_to_publish) -> None:
    # Semester creation, publication, and project insertion are one
    # transaction. Parsing and dry-run mode remain side-effect-free.
    with transaction.atomic():
        semester_by_key = {}
        for semester_key in {key for key, _fields in parsed_rows}:
            semester, _created = Semester.objects.get_or_create(
                year=semester_key[0],
                season=semester_key[1],
            )
            semester_by_key[semester_key] = semester
        if semesters_to_publish:
            Semester.objects.filter(
                pk__in=[semester_by_key[key].pk for key in semesters_to_publish if key in semester_by_key],
                is_published=False,
            ).update(is_published=True)
        rows_to_create = [
            Project(semester=semester_by_key[semester_key], **fields) for semester_key, fields in parsed_rows
        ]
        Project.objects.bulk_create(rows_to_create)


def import_projects_from_csv(csv_file, *, dry_run: bool = False, publish: bool = False) -> ImportResult:
    """
    Import projects from a CSV file (path string or file-like object).

    Returns an ImportResult with created/skipped counts and error details.
    """
    result = ImportResult()
    parsed_rows: list[tuple[tuple[int, int], dict[str, str]]] = []
    # Track (year, season, class_code, team_number) staged this run so a single
    # CSV containing internal duplicates does not insert them twice — the DB
    # existence check alone cannot see rows still pending in bulk_create.
    staged_keys: set[tuple] = set()
    semesters_to_publish: set[tuple[int, int]] = set()

    with _open_csv(csv_file) as fh:
        reader = csv.reader(fh)
        next(reader, None)  # skip header
        for line_no, row in enumerate(reader, start=2):
            parsed = _row_fields(row, line_no, result)
            if parsed is None:
                continue
            semester_key, fields = parsed
            dup_key = (*semester_key, fields["class_code"], fields["team_number"])
            if _already_imported(dup_key, staged_keys):
                result.skipped += 1
                continue
            staged_keys.add(dup_key)
            if publish:
                semesters_to_publish.add(semester_key)
            parsed_rows.append((semester_key, fields))

        if not dry_run:
            _save_rows(parsed_rows, semesters_to_publish)
        result.created = len(parsed_rows)
    return result
