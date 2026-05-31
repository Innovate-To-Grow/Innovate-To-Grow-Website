"""Frozen-page block validation helpers.

Mirrors the embed_widget block: the block references a FrozenPage by UUID and is
only valid when that page is published and actually captured (so the rendered
iframe won't 404).
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError

from .embed import validate_embed_sizing


def resolve_frozen_page(data):
    from apps.cms.models import FrozenPage

    raw_id = str(data.get("frozen_page_id", "")).strip()
    if not raw_id:
        raise ValidationError("Block type 'frozen_page' requires a non-empty 'frozen_page_id'.")
    try:
        uuid.UUID(raw_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(f"'frozen_page_id' is not a valid id: {raw_id!r}.") from exc

    frozen = FrozenPage.objects.filter(pk=raw_id).first()
    if frozen is None:
        raise ValidationError(f"No frozen page found with id '{raw_id}'. Import it under CMS > Frozen Pages first.")
    if not frozen.is_visible():
        raise ValidationError(
            f"Frozen page '{frozen.slug}' cannot be embedded: it is not published or has not been captured yet. "
            "Publish it (and re-freeze if needed) first."
        )
    return frozen


def validate_frozen_page_block(data):
    frozen = resolve_frozen_page(data)
    validate_embed_sizing(data)
    return frozen
