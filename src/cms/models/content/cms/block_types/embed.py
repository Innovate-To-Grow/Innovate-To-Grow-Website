"""Embed block validation helpers."""

import re

from django.core.exceptions import ValidationError

ASPECT_RATIO_RE = re.compile(r"^\d+:\d+$")

SANDBOX_TOKENS = {
    "allow-scripts",
    "allow-same-origin",
    "allow-forms",
    "allow-popups",
    "allow-popups-to-escape-sandbox",
    "allow-modals",
    "allow-downloads",
    "allow-presentation",
    "allow-orientation-lock",
    "allow-pointer-lock",
    "allow-storage-access-by-user-activation",
}

DEFAULT_SANDBOX = "allow-scripts allow-same-origin allow-forms allow-popups"


def validate_embed_block(data):
    from cms.services.embed_hosts import InvalidEmbedURL, is_host_allowed, parse_embed_url

    try:
        _, host = parse_embed_url(data.get("src", ""))
    except InvalidEmbedURL as exc:
        raise ValidationError(str(exc)) from exc

    if not is_host_allowed(host):
        raise ValidationError(
            f"Host '{host}' is not in the embed allowlist. Add it under CMS > Embed Allowed Hosts first."
        )

    validate_embed_sizing(data)
    if "sandbox" in data:
        sandbox = str(data.get("sandbox") or "").strip()
        data["sandbox"] = sandbox
        if sandbox:
            unknown = [t for t in sandbox.split() if t not in SANDBOX_TOKENS]
            if unknown:
                raise ValidationError(f"Unknown sandbox token(s): {', '.join(unknown)}.")


def validate_embed_widget_block(data):
    widget = resolve_embed_widget(data)
    validate_embed_sizing(data)
    normalized_embed_widget_hidden_sections(data, widget)
    return widget


def normalize_embed_widget_block_data(data):
    normalized = dict(data)
    widget = validate_embed_widget_block(normalized)
    hidden_sections = normalized_embed_widget_hidden_sections(normalized, widget)
    if hidden_sections or "hidden_sections" in normalized or normalized.get("hide_section_titles") is True:
        normalized["hidden_sections"] = hidden_sections
        normalized["hide_section_titles"] = "section_titles" in hidden_sections
    return normalized


def validate_embed_sizing(data):
    aspect_ratio = data.get("aspect_ratio")
    if aspect_ratio and not ASPECT_RATIO_RE.match(str(aspect_ratio)):
        raise ValidationError("'aspect_ratio' must look like '16:9' (digits:digits).")

    height = data.get("height")
    if height not in (None, ""):
        try:
            height_value = int(height)
        except (TypeError, ValueError) as exc:
            raise ValidationError("'height' must be a positive integer.") from exc
        if height_value <= 0 or height_value > 5000:
            raise ValidationError("'height' must be between 1 and 5000 pixels.")


def resolve_embed_widget(data):
    from cms.models import CMSEmbedWidget

    slug = str(data.get("slug", "")).strip().lower()
    if not slug:
        raise ValidationError("Block type 'embed_widget' requires a non-empty 'slug'.")

    widget = CMSEmbedWidget.objects.select_related("page").filter(slug=slug).first()
    if widget is None:
        raise ValidationError(
            f"No CMS embed widget found with slug '{slug}'. Create it under CMS > CMS Embed Widgets first."
        )
    if not widget.is_visible():
        if widget.widget_type == "blocks":
            raise ValidationError(
                f"CMS embed widget '{slug}' cannot be embedded: its source page is not published. "
                "Publish the source page first, or pick a different widget."
            )
        raise ValidationError(f"CMS embed widget '{slug}' cannot be embedded: its app route is not configured.")
    return widget


def normalized_embed_widget_hidden_sections(data, widget):
    from cms.embed_sections import normalize_hidden_sections

    if "hidden_sections" in data:
        return normalize_hidden_sections(data.get("hidden_sections"), widget.widget_type, widget.app_route)

    hidden_sections = ["section_titles"] if data.get("hide_section_titles") is True else []
    return normalize_hidden_sections(hidden_sections, widget.widget_type, widget.app_route)
