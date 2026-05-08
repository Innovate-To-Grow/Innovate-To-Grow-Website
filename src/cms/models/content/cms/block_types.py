import re

from django.core.exceptions import ValidationError

from cms.services.sanitize import validate_safe_url

BLOCK_TYPE_CHOICES = [
    ("hero", "Hero Banner"),
    ("rich_text", "Rich Text"),
    ("faq_list", "FAQ List"),
    ("link_list", "Link List"),
    ("cta_group", "CTA Buttons"),
    ("image_text", "Image + Text"),
    ("notice", "Notice / Callout"),
    ("contact_info", "Contact Info"),
    ("section_group", "Section Group"),
    ("table", "Data Table"),
    ("numbered_list", "Numbered List"),
    ("proposal_cards", "Proposal Cards"),
    ("navigation_grid", "Navigation Grid"),
    ("sponsor_year", "Sponsor Year"),
    ("embed", "Embed (iframe)"),
    ("embed_widget", "Embed CMS Widget"),
]

BLOCK_TYPE_KEYS = {choice[0] for choice in BLOCK_TYPE_CHOICES}

# Required fields per block type (for validation)
BLOCK_SCHEMAS = {
    "hero": {"required": [], "optional": ["heading", "subheading", "image_url", "image_alt"]},
    "rich_text": {"required": ["body_html"], "optional": ["heading", "heading_level"]},
    "faq_list": {"required": ["items"], "optional": ["heading"]},
    "link_list": {"required": ["items"], "optional": ["heading", "style"]},
    "cta_group": {"required": ["items"], "optional": []},
    "image_text": {"required": ["body_html"], "optional": ["image_url", "image_alt", "image_position", "heading"]},
    "notice": {"required": ["body_html"], "optional": ["heading", "style"]},
    "contact_info": {"required": ["items"], "optional": ["heading"]},
    "section_group": {"required": ["sections"], "optional": ["heading"]},
    "table": {"required": ["columns", "rows"], "optional": ["heading"]},
    "numbered_list": {"required": ["items"], "optional": ["heading", "preamble_html"]},
    "proposal_cards": {"required": ["proposals"], "optional": ["heading", "footer_html"]},
    "navigation_grid": {"required": ["items"], "optional": ["heading"]},
    "sponsor_year": {"required": ["year", "sponsors"], "optional": []},
    "embed": {
        "required": ["src"],
        "optional": ["heading", "title", "height", "aspect_ratio", "sandbox", "allow", "allowfullscreen"],
    },
    "embed_widget": {
        "required": ["slug"],
        "optional": ["heading", "height", "aspect_ratio", "hide_section_titles", "hidden_sections"],
    },
}

ASPECT_RATIO_RE = re.compile(r"^\d+:\d+$")

# Set of sandbox tokens the embed editor is allowed to emit. This is the
# conservative modern subset; `allow-top-navigation` is intentionally omitted
# so a malicious embed cannot redirect the parent page.
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


def validate_block_data(block_type, data):
    """Validate block data against its type schema."""
    if block_type not in BLOCK_SCHEMAS:
        raise ValidationError(f"Unknown block type: {block_type}")

    schema = BLOCK_SCHEMAS[block_type]
    for field in schema["required"]:
        if field not in data:
            raise ValidationError(f"Block type '{block_type}' requires field '{field}'.")

    if block_type == "sponsor_year":
        year = str(data.get("year", "")).strip()
        sponsors = data.get("sponsors")

        if not year:
            raise ValidationError("Block type 'sponsor_year' requires a non-empty 'year'.")
        if not isinstance(sponsors, list):
            raise ValidationError("Block type 'sponsor_year' requires 'sponsors' to be a list.")

        for index, sponsor in enumerate(sponsors):
            if not isinstance(sponsor, dict):
                raise ValidationError(f"Sponsor #{index + 1} must be an object.")
            if not str(sponsor.get("name", "")).strip():
                raise ValidationError(f"Sponsor #{index + 1} requires a non-empty 'name'.")

    if block_type == "link_list":
        _validate_link_list_urls(data)

    if block_type == "navigation_grid":
        _validate_navigation_grid_urls(data)

    if block_type == "contact_info":
        _validate_contact_info_urls(data)

    if block_type == "embed":
        _validate_embed_block(data)

    if block_type == "embed_widget":
        _validate_embed_widget_block(data)


def normalize_block_data_for_storage(block_type, data):
    """Return normalized block data for persistence after validation."""
    if block_type == "embed_widget":
        return _normalize_embed_widget_block_data(data)
    return data


def _validate_link_list_urls(data):
    items = data.get("items", [])
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        if url and not validate_safe_url(url):
            raise ValidationError(
                f"Link #{index + 1}: URL uses an unsafe scheme. Only http, https, mailto, and tel URLs are allowed."
            )


def _validate_navigation_grid_urls(data):
    items = data.get("items", [])
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        if url and not validate_safe_url(url):
            raise ValidationError(
                f"Navigation item #{index + 1}: URL uses an unsafe scheme. "
                "Only http, https, mailto, and tel URLs are allowed."
            )


def _validate_contact_info_urls(data):
    items = data.get("items", [])
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "url":
            continue
        value = item.get("value", "")
        if value and not validate_safe_url(value):
            raise ValidationError(
                f"Contact item #{index + 1}: URL uses an unsafe scheme. "
                "Only http, https, mailto, and tel URLs are allowed."
            )


def _validate_embed_block(data):
    from cms.services.embed_hosts import InvalidEmbedURL, is_host_allowed, parse_embed_url

    try:
        _, host = parse_embed_url(data.get("src", ""))
    except InvalidEmbedURL as exc:
        raise ValidationError(str(exc)) from exc

    if not is_host_allowed(host):
        raise ValidationError(
            f"Host '{host}' is not in the embed allowlist. Add it under CMS > Embed Allowed Hosts first."
        )

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

    if "sandbox" in data:
        # Normalize whitespace-only input (e.g. "   ") to empty string so the
        # frontend falls back to its default sandbox. A present-but-empty
        # sandbox attribute is the most restrictive policy and silently
        # breaks scripts/forms/popups even though the editor intended blank.
        sandbox = str(data.get("sandbox") or "").strip()
        data["sandbox"] = sandbox
        if sandbox:
            unknown = [t for t in sandbox.split() if t not in SANDBOX_TOKENS]
            if unknown:
                raise ValidationError(f"Unknown sandbox token(s): {', '.join(unknown)}.")


def _validate_embed_widget_block(data):
    widget = _resolve_embed_widget(data)

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

    _normalized_embed_widget_hidden_sections(data, widget)
    return widget


def _normalize_embed_widget_block_data(data):
    normalized = dict(data)
    widget = _validate_embed_widget_block(normalized)
    hidden_sections = _normalized_embed_widget_hidden_sections(normalized, widget)
    if hidden_sections or "hidden_sections" in normalized or normalized.get("hide_section_titles") is True:
        normalized["hidden_sections"] = hidden_sections
        normalized["hide_section_titles"] = "section_titles" in hidden_sections
    return normalized


def _resolve_embed_widget(data):
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


def _normalized_embed_widget_hidden_sections(data, widget):
    from cms.embed_sections import normalize_hidden_sections

    if "hidden_sections" in data:
        return normalize_hidden_sections(data.get("hidden_sections"), widget.widget_type, widget.app_route)

    hidden_sections = ["section_titles"] if data.get("hide_section_titles") is True else []
    return normalize_hidden_sections(hidden_sections, widget.widget_type, widget.app_route)
