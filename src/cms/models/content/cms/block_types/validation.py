"""Block data validation."""

from django.core.exceptions import ValidationError

from cms.services.sanitize import validate_safe_url

from .choices import BLOCK_SCHEMAS
from .embed import normalize_embed_widget_block_data, validate_embed_block, validate_embed_widget_block


def validate_block_data(block_type, data):
    """Validate block data against its type schema."""
    if block_type not in BLOCK_SCHEMAS:
        raise ValidationError(f"Unknown block type: {block_type}")

    schema = BLOCK_SCHEMAS[block_type]
    for field in schema["required"]:
        if field not in data:
            raise ValidationError(f"Block type '{block_type}' requires field '{field}'.")

    if block_type == "sponsor_year":
        _validate_sponsor_year(data)
    if block_type == "link_list":
        _validate_item_urls(data, prefix="Link")
    if block_type == "navigation_grid":
        _validate_item_urls(data, prefix="Navigation item")
    if block_type == "contact_info":
        _validate_contact_info_urls(data)
    if block_type == "embed":
        validate_embed_block(data)
    if block_type == "embed_widget":
        validate_embed_widget_block(data)


def normalize_block_data_for_storage(block_type, data):
    """Return normalized block data for persistence after validation."""
    if block_type == "embed_widget":
        return normalize_embed_widget_block_data(data)
    return data


def _validate_sponsor_year(data):
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


def _validate_item_urls(data, *, prefix):
    items = data.get("items", [])
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        if url and not validate_safe_url(url):
            raise ValidationError(
                f"{prefix} #{index + 1}: URL uses an unsafe scheme. "
                "Only http, https, mailto, and tel URLs are allowed."
            )


def _validate_contact_info_urls(data):
    items = data.get("items", [])
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("type") != "url":
            continue
        value = item.get("value", "")
        if value and not validate_safe_url(value):
            raise ValidationError(
                f"Contact item #{index + 1}: URL uses an unsafe scheme. "
                "Only http, https, mailto, and tel URLs are allowed."
            )
