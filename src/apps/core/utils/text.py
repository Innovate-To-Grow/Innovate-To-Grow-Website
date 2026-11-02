"""Whitespace clean-up for text imported from spreadsheets."""

import re

# str.split() treats NBSP, tabs and other Unicode spaces as whitespace, which is what a sheet cell carries.
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_SPACE_AROUND_NEWLINE = re.compile(r" ?\n ?")
_BLANK_LINES = re.compile(r"\n{3,}")


def collapse_whitespace(value: str) -> str:
    """One line of text: every run of whitespace (NBSP, tabs and line breaks included) becomes one space."""
    return " ".join(str(value or "").split())


def normalize_paragraphs(value: str) -> str:
    """Multi-line text: runs of spaces become one space, paragraph breaks are kept (at most one blank line)."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = _SPACE_AROUND_NEWLINE.sub("\n", text)
    return _BLANK_LINES.sub("\n\n", text).strip()
