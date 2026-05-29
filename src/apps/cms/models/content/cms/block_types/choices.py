"""CMS block type choices and schemas."""

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
