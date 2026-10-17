"""Rename past-project shares that were auto-named after a project.

Until this release, a share saved without a name was named after the collapsed text of its note or, when the note
had no text, after ``rows[0]["project_title"]``. Unnamed curations were therefore titled after one project (on the
shared page and in its PDF), or after the project details that "Insert projects into note" wrote at the top of the
note. The serializer now uses the first line of the owner's own note text, else "Past Project Curation"
(apps.projects.services.share_names).

Both derivations below are frozen copies of the code as it was when this migration landed; never import the live
serializer or service from here. Only shares created after names became optional (PR #335, merged
2026-06-19T22:48:45Z) can carry a derived name, and a share is renamed only when:

* its name is the truncated title of its first project, the share has more than one project, and the owner's own
  note text did not produce the name. The old code fell back to that title only when the note was empty at creation,
  so the new code would have given the generic title; this also covers notes added later, which never re-derived the
  name. A share never edited since it was created still has its creation note: when that note has text, the old code
  would have named the share after it, so the owner typed the title and the share is kept. A one-project share named
  after its only project is still accurate and is kept; or
* its name is exactly what the old code derives from its current note, and that note's own text (outside the
  inserted project details, structured or flattened by "Clear formatting") did not produce it, so the name came from
  inserted project details.

Renaming bumps ``version`` like any other document change, so an owner tab open during the deploy reloads once on its
next edit. Tasks still running the old code during a rolling deploy can create a few more auto-named shares after
this runs; owners can rename those with Edit Name. The reverse is a no-op.
"""

import html
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup, CData, NavigableString, Tag
from django.db import migrations
from django.db.models import F
from django.utils import timezone

NAMES_BECAME_OPTIONAL_AT = datetime(2026, 6, 19, 22, 48, 45, tzinfo=UTC)
# created_at and updated_at are stamped separately when a share is created, a few microseconds apart.
UNEDITED_TOLERANCE = timedelta(seconds=1)
NEW_DEFAULT_NAME = "Past Project Curation"
NAME_MAX_CHARS = 60
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
PROJECT_LABEL = r"Project \d+"
FIELD_LABEL = "(?:" + "|".join(re.escape(label) for label in INSERTED_FIELD_LABELS) + "):"
INSERTED_LABEL = re.compile(rf"{PROJECT_LABEL}|{FIELD_LABEL}")
INSERTED_LINE = re.compile(rf"{PROJECT_LABEL}(?:\s+{FIELD_LABEL}.*)?|{FIELD_LABEL}(?:\s.*)?")
SEPARATOR_LINE = re.compile(r"[-–—_=*·•\s]+")
TEXT_NEWLINE = re.compile(r"\r\n?|\n")
TEXT_TYPES = (NavigableString, CData)
END_OF_BLOCK = object()


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


def _is_invisible(char):
    return char.isspace() or unicodedata.category(char) == "Cf"


def _visible_text(text):
    return "".join(char for char in text if unicodedata.category(char) != "Cf").strip()


def _trim(text):
    text = re.sub(r"\s+", " ", text)
    start, end = 0, len(text)
    while start < end and _is_invisible(text[start]):
        start += 1
    while end > start and _is_invisible(text[end - 1]):
        end -= 1
    return text[start:end]


def _is_inserted_field(block):
    first = next(
        (child for child in block.children if not (isinstance(child, NavigableString) and not child.strip())), None
    )
    if not isinstance(first, Tag) or first.name != "strong":
        return False
    parts = []
    for child in first.children:
        if not isinstance(child, NavigableString):
            return False
        parts.append(str(child))
    return bool(INSERTED_LABEL.fullmatch(" ".join("".join(parts).split())))


def _note_lines(note):
    lines = []
    text = []

    def end_line():
        lines.append(TEXT_NEWLINE.split("".join(text)))
        text.clear()

    pending = list(reversed(BeautifulSoup(note or "", "html.parser").contents))
    while pending:
        node = pending.pop()
        if node is END_OF_BLOCK:
            end_line()
        elif isinstance(node, NavigableString):
            if type(node) in TEXT_TYPES:
                text.append(str(node))
        elif node.name == "br":
            end_line()
        elif node.name in ("div", "p"):
            if node.name == "div" and _is_inserted_field(node):
                continue
            end_line()
            pending.append(END_OF_BLOCK)
            pending.extend(reversed(node.contents))
        else:
            pending.extend(reversed(node.contents))
    end_line()
    return lines


def _is_inserted_line(text):
    return bool(INSERTED_LINE.fullmatch(_visible_text(text)))


def _owner_note_lines(note):
    """The note's lines without inserted project details, structured or flattened by "Clear formatting"."""
    lines = []
    for parts in _note_lines(note):
        trimmed = [_trim(part) for part in parts]
        first_text = next((part for part in trimmed if _visible_text(part)), "")
        if _is_inserted_line(first_text):
            continue
        lines.extend(part for part in trimmed if not _is_inserted_line(part))
    return lines


def new_default_name(note):
    """The fixed derivation: first line of the owner's own note text, else the generic title."""
    for line in _owner_note_lines(note):
        visible = _visible_text(line)
        if visible and not SEPARATOR_LINE.fullmatch(visible):
            return _truncate(line)
    return NEW_DEFAULT_NAME


def _owner_note_text(note):
    """The note's text outside the inserted project details, flattened the way the old code did."""
    return re.sub(r"\s+", " ", " ".join(_owner_note_lines(note))).strip()


def renamed_share_name(name, note, rows, created_at, updated_at):
    """The name an auto-named share should get, or None to leave the share as it is."""
    if not name or created_at < NAMES_BECAME_OPTIONAL_AT:
        return None
    owner_text = _owner_note_text(note)
    if owner_text and _truncate(owner_text) == name:
        return None
    rows = rows or []
    first_title = _truncate(str((rows[0] or {}).get("project_title", "") or "").strip()) if rows else ""
    if first_title and name == first_title:
        unedited = updated_at is not None and updated_at - created_at < UNEDITED_TOLERANCE
        if len(rows) < 2 or (unedited and _old_flatten(note)):
            return None
        return NEW_DEFAULT_NAME
    if name == old_default_name(note, rows):
        new_name = new_default_name(note)
        return new_name if new_name != name else None
    return None


def rename_auto_named_shares(apps, schema_editor):
    PastProjectShare = apps.get_model("projects", "PastProjectShare")
    shares = (
        PastProjectShare.objects.filter(created_at__gte=NAMES_BECAME_OPTIONAL_AT)
        .exclude(name="")
        .only("pk", "name", "note", "rows", "created_at", "updated_at")
        .order_by("created_at")
    )
    for share in shares.iterator():
        new_name = renamed_share_name(share.name, share.note, share.rows, share.created_at, share.updated_at)
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
