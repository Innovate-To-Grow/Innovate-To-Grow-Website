# CMS Block Types

## Supported blocks

- `rich_text`: requires `body_html`; optional `heading` and `heading_level`
- `hero`: all fields optional
- `faq_list`: requires `items`; optional `heading`
- `link_list`: requires `items`; optional `heading` and `style`
- `cta_group`: requires `items`
- `image_text`: requires `body_html`; optional `heading`, `image_url`, `image_alt`, and `image_position`
- `notice`: requires `body_html`; optional `heading` and `style`
- `contact_info`: requires `items`; optional `heading`
- `navigation_grid`: requires `items`; optional `heading`
- `table`: requires `columns` and `rows`; optional `heading`
- `numbered_list`: requires `items`; optional `heading` and `preamble_html`
- `section_group`: requires `sections`; optional `heading`
- `proposal_cards`: requires `proposals`; optional `heading` and `footer_html`
- `google_sheet`: requires `sheet_source_slug`; optional `heading`, `sheet_view_slug`, and `display_mode`
- `schedule_grid`: requires `sheet_source_slug`; optional `heading`

## Contact item types

- `email`
- `phone`
- `text`
- `link`
