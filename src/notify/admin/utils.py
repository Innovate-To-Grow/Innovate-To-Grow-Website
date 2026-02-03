import re

from django.utils.html import escape

_HIGHLIGHT_STYLE = (
    "<style>"
    ".preview-highlight{background:#fff2a8;padding:1px 3px;border-radius:3px;"
    "box-shadow: inset 0 0 0 1px rgba(140,120,0,0.25);}"
    "</style>"
)


def _inject_preview_style(html: str) -> str:
    if "preview-highlight" in html:
        return html
    if "<head>" in html:
        return html.replace("<head>", "<head>" + _HIGHLIGHT_STYLE, 1)
    return _HIGHLIGHT_STYLE + html


def _highlight_values(html: str, values: list[str]) -> str:
    if not values:
        return html

    parts = re.split(r"(<[^>]+>)", html)
    for idx, part in enumerate(parts):
        if part.startswith("<"):
            continue
        updated = part
        for value in values:
            if not value:
                continue
            candidates = {str(value), escape(str(value))}
            for candidate in candidates:
                if not candidate:
                    continue
                updated = updated.replace(
                    candidate,
                    f'<span class="preview-highlight">{candidate}</span>',
                )
        parts[idx] = updated
    return "".join(parts)


def _collect_highlight_values(context: dict, subject: str | None = None) -> list[str]:
    keys = [
        "recipient_name",
        "user_name",
        "recipient_email",
        "code",
        "verification_link",
        "link",
        "expires_in_minutes",
        "preheader",
    ]
    values = [str(context.get(key)) for key in keys if context.get(key) not in (None, "")]
    if subject:
        values.append(subject)
    return values
