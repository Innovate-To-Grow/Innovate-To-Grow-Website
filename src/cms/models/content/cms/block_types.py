from django.core.exceptions import ValidationError

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
}


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
