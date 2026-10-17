"""Default names for past-project shares (curations) whose owner leaves the name blank.

The original request was "is the name necessary? … or just a default e.g. the first N characters of the
curation". The default is therefore the first line the owner wrote in the curation note. It is never a
project's title: the old fallback to the first row's project title made a whole curation look like it was
about one project, on the shared page and in its PDF/Word/Excel exports.
"""

import re
import unicodedata

from bs4 import BeautifulSoup, CData, NavigableString, Tag

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
_PROJECT_LABEL = r"Project \d+"
_FIELD_LABEL = "(?:" + "|".join(re.escape(label) for label in _INSERTED_FIELD_LABELS) + "):"
_INSERTED_LABEL = re.compile(rf"{_PROJECT_LABEL}|{_FIELD_LABEL}")
# The same lines once "Clear formatting" has flattened the inserted block to plain text. A field line carries its
# value; a project line is the bare "Project N", so an owner's "Project 3 finalists" is still the owner's line.
_INSERTED_LINE = re.compile(rf"{_PROJECT_LABEL}(?:\s+{_FIELD_LABEL}.*)?|{_FIELD_LABEL}(?:\s.*)?")
# Fields whose value can run over several lines. Once "Clear formatting" removed their <div>, only the first line
# carries the label, so the lines after it go too.
_MULTILINE_FIELD = re.compile(r"(?:Abstract|Students):(?:\s.*)?")
# Lines made only of dashes or rules, like the separator the insert puts between projects.
_SEPARATOR_LINE = re.compile(r"[-–—_=*·•\s]+")
# Newlines inside text are line breaks too: pasted text keeps them and the note is shown with white-space: pre-wrap.
_TEXT_NEWLINE = re.compile(r"\r\n?|\n")
# Text nodes that count as note text (comments and similar nodes do not), and the marker for the end of a block.
_TEXT_TYPES = (NavigableString, CData)
_END_OF_BLOCK = object()


# Invisible characters dropped from the ends of a name: zero-width spaces and joiners, bidi marks, soft hyphens and
# BOMs, which only make a line look blank. Other format characters, such as the tag characters that make up
# subdivision flags, are kept.
_EDGE_INVISIBLE = frozenset(
    map(
        chr,
        (
            0x00AD,  # soft hyphen
            0x200B,  # zero-width space
            0x200C,  # zero-width non-joiner
            0x200D,  # zero-width joiner
            0x200E,  # left-to-right mark
            0x200F,  # right-to-left mark
            *range(0x202A, 0x202F),  # bidi embeddings and overrides
            *range(0x2060, 0x2065),  # word joiner, invisible operators
            *range(0x2066, 0x206A),  # bidi isolates
            0xFEFF,  # byte order mark
        ),
    )
)


def _is_edge_invisible(char: str) -> bool:
    return char.isspace() or char in _EDGE_INVISIBLE


def _visible_text(text: str) -> str:
    return "".join(char for char in text if unicodedata.category(char) != "Cf").strip()


def _trim(text: str) -> str:
    """Collapse whitespace and drop invisible characters at the ends; those inside the text (emoji, Persian) stay."""
    text = re.sub(r"\s+", " ", text)
    start, end = 0, len(text)
    while start < end and _is_edge_invisible(text[start]):
        start += 1
    while end > start and _is_edge_invisible(text[end - 1]):
        end -= 1
    return text[start:end]


def _plain_label(element: Tag) -> str | None:
    """The text of an element holding only text, else None. Never flattens a nested subtree, so this stays cheap."""
    parts = []
    for child in element.children:
        if not isinstance(child, NavigableString):
            return None
        parts.append(str(child))
    return " ".join("".join(parts).split())


def _first_meaningful_child(block: Tag):
    for child in block.children:
        if isinstance(child, NavigableString) and not child.strip():
            continue
        return child
    return None


def _is_inserted_field(block: Tag) -> bool:
    first = _first_meaningful_child(block)
    if not isinstance(first, Tag) or first.name != "strong":
        return False
    label = _plain_label(first)
    return label is not None and bool(_INSERTED_LABEL.fullmatch(label))


def _note_lines(note: str) -> list[list[str]]:
    """The note's lines, split at <br>, <div> and <p>, each as its newline-separated parts.

    One pass over the parsed note, without editing the tree: bs4 tree edits walk the nesting depth, which made a
    deeply nested note quadratic.
    """
    lines: list[list[str]] = []
    text: list[str] = []

    def end_line():
        lines.append(_TEXT_NEWLINE.split("".join(text)))
        text.clear()

    pending = list(reversed(BeautifulSoup(note or "", "html.parser").contents))
    while pending:
        node = pending.pop()
        if node is _END_OF_BLOCK:
            end_line()
        elif isinstance(node, NavigableString):
            if type(node) in _TEXT_TYPES:
                text.append(str(node))
        elif node.name == "br":
            end_line()
        elif node.name in ("div", "p"):
            # An inserted field is dropped whole, so a multi-line abstract never leaks its later lines.
            if node.name == "div" and _is_inserted_field(node):
                continue
            end_line()
            pending.append(_END_OF_BLOCK)
            pending.extend(reversed(node.contents))
        else:
            pending.extend(reversed(node.contents))
    end_line()
    return lines


def _is_inserted_line(text: str) -> bool:
    return bool(_INSERTED_LINE.fullmatch(_visible_text(text)))


def _owner_note_lines(note: str) -> list[str]:
    """The note's lines without inserted project details: blank and separator lines are kept, trimmed."""
    lines = []
    for parts in _note_lines(note):
        trimmed = [_trim(part) for part in parts]
        first_text = next((part for part in trimmed if _visible_text(part)), "")
        if _MULTILINE_FIELD.fullmatch(_visible_text(first_text)):
            continue
        lines.extend(part for part in trimmed if not _is_inserted_line(part))
    return lines


def _truncate(text: str) -> str:
    if len(text) > DEFAULT_NAME_MAX_CHARS:
        return text[: DEFAULT_NAME_MAX_CHARS - 1].rstrip() + "…"
    return text


def default_share_name(note: str) -> str:
    """The first line of the owner's own note text (truncated), else ``DEFAULT_SHARE_NAME``."""
    for line in _owner_note_lines(note):
        visible = _visible_text(line)
        if visible and not _SEPARATOR_LINE.fullmatch(visible):
            return _truncate(line)
    return DEFAULT_SHARE_NAME
