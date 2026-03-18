---
name: add-cms-page
description: Create a new CMS page with content blocks via Django shell. Use when the user asks to add a page to the website (e.g. "add an about page", "create a FAQ page", "new CMS page for sponsors").
argument-hint: [page description or content requirements]
allowed-tools: Bash(python manage.py shell*), Bash(cd src*), Read
---

# Add CMS Page

Create a new CMS page for: $ARGUMENTS

## Instructions

You are creating a CMS page in a Django project. CMS pages are stored in the database via the `CMSPage` and `CMSBlock` models. The frontend automatically renders any published CMS page at its route.

### Step 1: Determine page details from the user's request

- **slug**: lowercase, hyphen-separated identifier (e.g. `about`, `contact-us`, `sponsor-info`)
- **route**: URL path with leading slash, no trailing slash (e.g. `/about`, `/contact-us`)
- **title**: display title
- **page_css_class**: CSS class for styling (e.g. `about-page`). Use `{slug}-page` convention.
- **status**: `draft` (default) or `published`
- **blocks**: ordered list of content blocks (see Block Types Reference below)

### Step 2: Check for conflicts

Before creating, run a Django shell command to verify no existing page uses the same slug or route:

```python
cd src && python manage.py shell -c "
from pages.models import CMSPage
print('slug exists:', CMSPage.all_objects.filter(slug='THE_SLUG').exists())
print('route exists:', CMSPage.all_objects.filter(route='/THE_ROUTE').exists())
"
```

### Step 3: Create the page via Django shell

Run a single Django shell script that creates the CMSPage and all its CMSBlocks. Example pattern:

```python
cd src && python manage.py shell -c "
from pages.models import CMSPage, CMSBlock

page = CMSPage(
    slug='example',
    route='/example',
    title='Example Page',
    page_css_class='example-page',
    status='draft',
    sort_order=0,
)
page.save()

CMSBlock.objects.create(
    page=page,
    block_type='rich_text',
    sort_order=0,
    admin_label='Main content',
    data={
        'heading': 'Example',
        'heading_level': 1,
        'body_html': '<p>Content here.</p>',
    },
)

print(f'Created page: {page.title} ({page.route}) [{page.status}]')
print(f'Blocks: {page.blocks.count()}')
"
```

### Step 4: Register the route (if needed)

- **CMS pages do NOT need a frontend route entry** — the catch-all `*` route in `pages/src/router/index.tsx` renders `<CMSPageComponent/>` for any unmatched path.
- **Only add an explicit route** if the page needs to appear before the catch-all (rare).
- **For non-CMS data-driven pages** (with custom API calls), add to `APP_ROUTES` in `src/pages/app_routes.py`.

### Step 5: Verify

After creating, verify the page exists:

```python
cd src && python manage.py shell -c "
from pages.models import CMSPage
p = CMSPage.objects.get(slug='THE_SLUG')
print(f'{p.title} | route={p.route} | status={p.status} | blocks={p.blocks.count()}')
for b in p.blocks.order_by('sort_order'):
    print(f'  [{b.sort_order}] {b.block_type}: {b.admin_label}')
"
```

If status is `published`, tell the user to visit `http://localhost:5173{route}` to see the page.

## Block Types Reference

### rich_text
Most common block. Renders HTML content with optional heading.
```python
{"heading": "Title", "heading_level": 1, "body_html": "<p>Content</p>"}
# Required: body_html | Optional: heading, heading_level
```

### hero
Banner section at the top of a page.
```python
{"heading": "Welcome", "subheading": "Subtitle", "image_url": "/media/hero.jpg", "image_alt": "Description"}
# All fields optional
```

### faq_list
List of question/answer pairs.
```python
{"heading": "FAQs", "items": [{"question": "Q?", "answer_html": "<p>A.</p>"}]}
# Required: items | Optional: heading
```

### link_list
List of links, optionally styled.
```python
{"heading": "Resources", "style": "card", "items": [{"label": "Link", "url": "/path", "is_external": false}]}
# Required: items | Optional: heading, style
```

### cta_group
Call-to-action buttons.
```python
{"items": [{"text": "Get Started", "url": "/register", "style": "primary"}]}
# Required: items
```

### image_text
Image alongside text content.
```python
{"heading": "About", "image_url": "/media/photo.jpg", "image_alt": "Photo", "image_position": "right", "body_html": "<p>Text</p>"}
# Required: body_html | Optional: heading, image_url, image_alt, image_position
```

### notice
Callout/alert box.
```python
{"heading": "Important", "style": "info", "body_html": "<p>Notice text</p>"}
# Required: body_html | Optional: heading, style (info/warning/success/error)
```

### contact_info
Contact details list.
```python
{"heading": "Contact", "items": [{"label": "Email", "value": "mail@example.com", "type": "email"}]}
# Required: items | Optional: heading
# Item types: email, phone, text, link
```

### navigation_grid
Grid of linked cards.
```python
{"heading": "Explore", "items": [{"title": "Card", "description": "Desc", "url": "/path", "is_external": false}]}
# Required: items | Optional: heading
```

### table
Data table with columns and rows.
```python
{"heading": "Data", "columns": ["Name", "Role"], "rows": [["Alice", "Engineer"], ["Bob", "Designer"]]}
# Required: columns, rows | Optional: heading
```

### numbered_list
Ordered list with optional preamble.
```python
{"heading": "Steps", "preamble_html": "<p>Follow these steps:</p>", "items": ["Step one", "Step two"]}
# Required: items | Optional: heading, preamble_html
```

### section_group
Groups multiple sub-sections together.
```python
{"heading": "Overview", "sections": [{"heading": "Part 1", "body_html": "<p>...</p>"}]}
# Required: sections | Optional: heading
```

### proposal_cards
Project proposal display cards.
```python
{"heading": "Proposals", "proposals": [{"type": "Capstone", "title": "Project", "organization": "Org", "background": "...", "problem": "...", "objectives": "..."}]}
# Required: proposals | Optional: heading, footer_html
```

### google_sheet
Embed data from a GoogleSheetSource.
```python
{"heading": "Data", "sheet_source_slug": "current-event", "display_mode": "table"}
# Required: sheet_source_slug | Optional: heading, sheet_view_slug, display_mode
```

### schedule_grid
Event schedule from a sheet source.
```python
{"heading": "Schedule", "sheet_source_slug": "current-event"}
# Required: sheet_source_slug | Optional: heading
```

## Important Notes

- Always use `--settings=core.settings.dev` is NOT needed for `manage.py shell` — the DJANGO_SETTINGS_MODULE env var or default in manage.py handles it.
- Route must be unique across all CMS pages (including soft-deleted ones in `all_objects`).
- Slug must be unique. Convention: match the route without slashes (e.g. route `/about` → slug `about`).
- `body_html` fields accept full HTML. Use semantic tags (`<p>`, `<h2>`, `<ul>`, `<a>`).
- After creating a page, cache may need clearing. The signal handlers auto-clear on save, so this is usually automatic.
- If the user wants to publish immediately, set `status='published'`. Otherwise default to `'draft'`.
