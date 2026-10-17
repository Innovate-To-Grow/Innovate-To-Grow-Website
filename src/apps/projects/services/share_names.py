"""Default names for past-project shares (curations) whose owner leaves the name blank.

The original request was "is the name necessary? … or just a default e.g. the first N characters of the
curation". The default is therefore the first line the owner wrote in the curation note. It is never a
project's title: the old fallback to the first row's project title made a whole curation look like it was
about one project, on the shared page and in its PDF/Word/Excel exports.
"""

import re

from bs4 import BeautifulSoup, NavigableString, Tag

DEFAULT_SHARE_NAME = "Past Project Curation"
DEFAULT_NAME_MAX_CHARS = 60

# "Insert projects into note" (pastProjectsDetailText.ts) writes every project as one line per field, such as
# <div><strong>Project 1</strong></div> and <div><strong>Abstract:</strong> …</div>. Those lines are project data,
# not the owner's words, so they never name the curation. Text the owner types inside the inserted block (browsers
# put a heading typed above it there) still counts. Keep the labels in sync with PAST_PROJECT_NOTE_INSERT_FIELDS.
_INSERTED_FIELD_LABELS = (
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
_INSERTED_LABELS_PATTERN = "|".join(re.escape(label) for label in _INSERTED_FIELD_LABELS)
_INSERTED_LABEL = re.compile(rf"Project \d+|(?:{_INSERTED_LABELS_PATTERN}):")
# The same lines once "Clear formatting" has flattened the inserted block to plain text.
_INSERTED_LINE = re.compile(rf"(?:{_INSERTED_LABEL.pattern})(?:\s.*)?")
# Lines made only of dashes or rules, like the separator the insert puts between projects.
_SEPARATOR_LINE = re.compile(r"[-–—_=*·•\s]+")
# Invisible characters that str.strip() and \s keep, which would otherwise make a blank-looking name.
_INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def _first_meaningful_child(block: Tag):
    for child in block.children:
        if isinstance(child, NavigableString) and not child.strip():
            continue
        return child
    return None


def _is_inserted_field(block: Tag) -> bool:
    first = _first_meaningful_child(block)
    return (
        isinstance(first, Tag)
        and first.name == "strong"
        and bool(_INSERTED_LABEL.fullmatch(first.get_text(" ", strip=True)))
    )


def _note_lines(note: str) -> list[str]:
    soup = BeautifulSoup(note or "", "html.parser")
    # Drop inserted field lines as whole blocks first, so a multi-line abstract never leaks its later lines.
    for block in soup.find_all("div"):
        if not block.decomposed and _is_inserted_field(block):
            block.decompose()
    for line_break in soup.find_all("br"):
        line_break.replace_with("\n")
    for block in soup.find_all(("div", "p")):
        block.insert_before("\n")
        block.append("\n")
    return soup.get_text().split("\n")


def _truncate(text: str) -> str:
    if len(text) > DEFAULT_NAME_MAX_CHARS:
        return text[: DEFAULT_NAME_MAX_CHARS - 1].rstrip() + "…"
    return text


def default_share_name(note: str) -> str:
    """The first line of the owner's own note text (truncated), else ``DEFAULT_SHARE_NAME``."""
    for raw_line in _note_lines(note):
        line = re.sub(r"\s+", " ", _INVISIBLE.sub("", raw_line)).strip()
        if line and not _SEPARATOR_LINE.fullmatch(line) and not _INSERTED_LINE.fullmatch(line):
            return _truncate(line)
    return DEFAULT_SHARE_NAME
