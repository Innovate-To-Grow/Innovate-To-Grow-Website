"""Rename past-project shares that were auto-named after a project.

Until this release, a share saved without a name was named after the collapsed text of its note or, when the note
had no text, after ``rows[0]["project_title"]``. Unnamed curations were therefore titled after one project (on the
shared page and in its PDF), or after the project details that "Insert projects into note" wrote at the top of the
note. The serializer now uses the first line of the owner's own note text, else "Past Project Curation"
(apps.projects.services.share_names).

Both derivations below are frozen copies of the code as it was when this migration landed; never import the live
serializer or service from here. Only shares created after names became optional (PR #335, merged
2026-06-19T22:48:45Z) can carry a derived name, and a share is renamed only when:

* its name is the truncated title of its first project, and the owner's own note text did not produce it (the old
  code fell back to that title only when the note was empty at creation, so the new code would have given the
  generic title; this also covers notes added later, which never re-derived the name). A one-project share named
  after its only project is still accurate and is kept; or
* its name is exactly what the old code derives from its current note, and that note's own text (outside the
  inserted project details) did not produce it, so the name came from inserted project details.

Renaming bumps ``version`` like any other document change, so an owner tab open during the deploy reloads once on its
next edit. Tasks still running the old code during a rolling deploy can create a few more auto-named shares after
this runs; owners can rename those with Edit Name. The reverse is a no-op.
"""

import html
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup, NavigableString, Tag
from django.db import migrations
from django.db.models import F
from django.utils import timezone

NAMES_BECAME_OPTIONAL_AT = datetime(2026, 6, 19, 22, 48, 45, tzinfo=UTC)
NEW_DEFAULT_NAME = "Past Project Curation"
NAME_MAX_CHARS = 60
PROJECT_SUMMARY_SELECTOR = 'div[data-past-project-note-curation="project-summary"]'
INSERTED_FIELD_LABELS = (
    "Year-Semester",
    "Class / Team#",
    "Team Name",
    "Project Title",
    "Individual Link",
    "Organization",
    "Industry",
    "Students",
    "Abstract",
)
INSERTED_LABELS_PATTERN = "|".join(re.escape(label) for label in INSERTED_FIELD_LABELS)
INSERTED_LABEL = re.compile(rf"Project \d+|(?:{INSERTED_LABELS_PATTERN}):")
INSERTED_LINE = re.compile(rf"(?:{INSERTED_LABEL.pattern})(?:\s.*)?")
SEPARATOR_LINE = re.compile(r"[-–—_=*·•\s]+")
INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def _truncate(text):
    if len(text) > NAME_MAX_CHARS:
        return text[: NAME_MAX_CHARS - 1].rstrip() + "…"
    return text


def _old_flatten(note):
    if not note:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", note))).strip()


def old_default_name(note, rows):
    """The pre-fix derivation: collapsed note text, else the first row's project title."""
    candidate = _old_flatten(note)
    if not candidate and rows:
        candidate = str((rows[0] or {}).get("project_title", "") or "").strip()
    candidate = candidate.strip()
    if not candidate:
        return "Untitled curation"
    return _truncate(candidate)


def _is_inserted_field(block):
    first = next(
        (child for child in block.children if not (isinstance(child, NavigableString) and not child.strip())), None
    )
    return isinstance(first, Tag) and first.name == "strong" and bool(
        INSERTED_LABEL.fullmatch(first.get_text(" ", strip=True))
    )


def new_default_name(note):
    """The fixed derivation: first line of the owner's own note text, else the generic title."""
    soup = BeautifulSoup(note or "", "html.parser")
    for block in soup.find_all("div"):
        if not block.decomposed and _is_inserted_field(block):
            block.decompose()
    for line_break in soup.find_all("br"):
        line_break.replace_with("\n")
    for block in soup.find_all(("div", "p")):
        block.insert_before("\n")
        block.append("\n")
    for raw_line in soup.get_text().split("\n"):
        line = re.sub(r"\s+", " ", INVISIBLE.sub("", raw_line)).strip()
        if line and not SEPARATOR_LINE.fullmatch(line) and not INSERTED_LINE.fullmatch(line):
            return _truncate(line)
    return NEW_DEFAULT_NAME


def _owner_note_text(note):
    """The note's text outside the inserted project details, flattened the way the old code did."""
    soup = BeautifulSoup(note or "", "html.parser")
    for block in soup.select(PROJECT_SUMMARY_SELECTOR):
        block.decompose()
    return _old_flatten(str(soup))


def renamed_share_name(name, note, rows, created_at):
    """The name an auto-named share should get, or None to leave the share as it is."""
    if not name or created_at < NAMES_BECAME_OPTIONAL_AT:
        return None
    owner_text = _owner_note_text(note)
    if owner_text and _truncate(owner_text) == name:
        return None
    rows = rows or []
    first_title = _truncate(str((rows[0] or {}).get("project_title", "") or "").strip()) if rows else ""
    if first_title and name == first_title:
        return NEW_DEFAULT_NAME if len(rows) > 1 else None
    if name == old_default_name(note, rows):
        new_name = new_default_name(note)
        return new_name if new_name != name else None
    return None


def rename_auto_named_shares(apps, schema_editor):
    PastProjectShare = apps.get_model("projects", "PastProjectShare")
    shares = PastProjectShare.objects.only("pk", "name", "note", "rows", "created_at").order_by("created_at")
    for share in shares.iterator():
        new_name = renamed_share_name(share.name, share.note, share.rows, share.created_at)
        if new_name is None:
            continue
        renamed = PastProjectShare.objects.filter(pk=share.pk, name=share.name).update(
            name=new_name, version=F("version") + 1, updated_at=timezone.now()
        )
        if renamed:
            print(f"\n  Renamed past-project share {share.pk}: {share.name!r} -> {new_name!r}")


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0009_active_sheet_config_invariant"),
    ]

    operations = [
        migrations.RunPython(rename_auto_named_shares, migrations.RunPython.noop),
    ]
