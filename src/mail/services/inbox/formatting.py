from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup


def format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %I:%M %p").strip()
    if value:
        return str(value)
    return ""


def build_snippet(message: Any) -> str:
    html = str(getattr(message, "html", "") or "").strip()
    text = str(getattr(message, "text", "") or "").strip()
    source = html or text
    if not source:
        return ""
    snippet = " ".join(BeautifulSoup(source, "html.parser").get_text(" ").split())
    return snippet[:197].rstrip() + "..." if len(snippet) > 200 else snippet


def extract_from(message: Any) -> tuple[str, str]:
    from_values = getattr(message, "from_values", None)
    if from_values:
        return (
            str(getattr(from_values, "name", "") or ""),
            str(getattr(from_values, "email", "") or ""),
        )
    return "", str(getattr(message, "from_", "") or "")


def extract_to(message: Any) -> list[dict[str, str]]:
    to_values = getattr(message, "to_values", None) or []
    return [
        {
            "name": str(getattr(value, "name", "") or ""),
            "email": str(getattr(value, "email", "") or ""),
        }
        for value in to_values
    ]
