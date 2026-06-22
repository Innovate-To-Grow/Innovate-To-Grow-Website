"""
CSV import service for past projects.

Parses CSV files exported from the legacy "Project Resources" Google Sheet
and creates Semester + Project records.
"""

import csv
import io
import re
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


def _parse_semester(value: str) -> Semester | None:
    match = YEAR_SEMESTER_RE.match(value.strip())
    if not match:
        return None
    year, season = int(match.group(1)), int(match.group(2))
    semester, created = Semester.objects.get_or_create(year=year, season=season)
    return semester


def import_projects_from_csv(csv_file, *, dry_run: bool = False, publish: bool = False) -> ImportResult:
    """
    Import projects from a CSV file (path string or file-like object).

    Returns an ImportResult with created/skipped counts and error details.
    """
    result = ImportResult()

    if isinstance(csv_file, str | bytes):
        # file path
        fh = open(csv_file, newline="", encoding="utf-8-sig")
        should_close = True
    else:
        # file-like (e.g. Django UploadedFile)
        content = csv_file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        fh = io.StringIO(content)
        should_close = False

    try:
        reader = csv.reader(fh)
        next(reader, None)  # skip header

        rows_to_create = []
        # Track (semester_pk, class_code, team_number) staged this run so a single
        # CSV containing internal duplicates does not insert them twice — the DB
        # existence check alone cannot see rows still pending in bulk_create.
        staged_keys: set[tuple] = set()
        semesters_to_publish: set = set()

        for line_no, row in enumerate(reader, start=2):
            if len(row) < 5:
                continue

            year_sem = row[0].strip()
            if not year_sem:
                continue

            semester = _parse_semester(year_sem)
            if semester is None:
                result.errors.append(f"Row {line_no}: unparseable Year-Semester '{year_sem}'")
                continue

            fields = {}
            for idx, field_name in FIELD_INDICES.items():
                fields[field_name] = row[idx].strip() if idx < len(row) else ""

            if not fields.get("project_title"):
                result.errors.append(f"Row {line_no}: missing project_title, skipped")
                continue

            # Duplicate check: same semester + class_code + team_number, against
            # both already-persisted rows and rows staged earlier in this import.
            dup_key = (semester.pk, fields["class_code"], fields["team_number"])
            if (
                dup_key in staged_keys
                or Project.objects.filter(
                    semester=semester,
                    class_code=fields["class_code"],
                    team_number=fields["team_number"],
                ).exists()
            ):
                result.skipped += 1
                continue

            staged_keys.add(dup_key)
            if publish and not semester.is_published:
                semesters_to_publish.add(semester.pk)
            rows_to_create.append(Project(semester=semester, **fields))

        if not dry_run:
            # Publish semesters and insert projects in one transaction so a failed
            # insert does not leave semesters published with no projects.
            with transaction.atomic():
                if semesters_to_publish:
                    Semester.objects.filter(pk__in=semesters_to_publish, is_published=False).update(is_published=True)
                Project.objects.bulk_create(rows_to_create)
        result.created = len(rows_to_create)
    finally:
        if should_close:
            fh.close()

    return result
