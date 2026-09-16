"""Embed block validation helpers."""

import re
import uuid

from django.core.exceptions import ValidationError

ASPECT_RATIO_RE = re.compile(r"^\d+:\d+$")

SCHEDULE_APP_ROUTE = "/schedule"
# Canonical hyphenated form only — the SPA (embedScheduleId.ts) accepts exactly
# this shape off the iframe URL, and some write paths (AI page creation) store
# validated data without the storage normalization below.
SCHEDULE_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

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
    from apps.cms.services.sanitization.embed_hosts import InvalidEmbedURL, is_host_allowed, parse_embed_url

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
    normalized_embed_widget_schedule_id(data, widget)
    return widget


def normalize_embed_widget_block_data(data):
    normalized = dict(data)
    widget = validate_embed_widget_block(normalized)
    hidden_sections = normalized_embed_widget_hidden_sections(normalized, widget)
    if hidden_sections or "hidden_sections" in normalized or normalized.get("hide_section_titles") is True:
        normalized["hidden_sections"] = hidden_sections
        normalized["hide_section_titles"] = "section_titles" in hidden_sections
    schedule_id = normalized_embed_widget_schedule_id(normalized, widget)
    if schedule_id:
        normalized["schedule_id"] = schedule_id
    else:
        normalized.pop("schedule_id", None)
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
    from apps.cms.models import CMSEmbedWidget

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


def normalized_embed_widget_schedule_id(data, widget):
    """Return the block-level schedule override as a canonical UUID string, or "".

    A block may pin a specific ``CurrentProjectSchedule`` (e.g. a previous
    year's) so one ``/schedule`` widget can be reused across pages. The
    override beats the widget's own ``schedule`` FK, which in turn beats the
    active schedule.
    """
    raw = data.get("schedule_id")
    if isinstance(raw, str):
        raw = raw.strip()
    if raw in (None, ""):
        return ""
    if widget.widget_type != "app_route" or widget.app_route != SCHEDULE_APP_ROUTE:
        raise ValidationError("'schedule_id' is only supported for widgets that embed the /schedule app route.")
    if not isinstance(raw, str) or not SCHEDULE_ID_RE.match(raw):
        raise ValidationError("'schedule_id' must be a schedule UUID.")
    schedule_pk = uuid.UUID(raw)

    from apps.event.models import CurrentProjectSchedule

    if not CurrentProjectSchedule.objects.filter(pk=schedule_pk).exists():
        raise ValidationError(
            f"No schedule found with id '{schedule_pk}'. Pick one from Events > Current Project and Schedule."
        )
    return str(schedule_pk)


def normalized_embed_widget_hidden_sections(data, widget):
    from apps.cms.services.embed.embed_sections import normalize_hidden_sections

    if "hidden_sections" in data:
        return normalize_hidden_sections(data.get("hidden_sections"), widget.widget_type, widget.app_route)

    hidden_sections = ["section_titles"] if data.get("hide_section_titles") is True else []
    return normalize_hidden_sections(hidden_sections, widget.widget_type, widget.app_route)
