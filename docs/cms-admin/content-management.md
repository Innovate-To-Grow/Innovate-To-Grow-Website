# Content Management

How content is created, organized, and published through the CMS.

## CMS pages

### Model: `CMSPage`

Each page represents a frontend-routable URL. Key fields:

| Field | Purpose |
|-------|---------|
| `slug` | URL-friendly identifier |
| `route` | Full URL path (unique, used for frontend routing) |
| `title` | Page title |
| `meta_description` | SEO meta description |
| `status` | `draft`, `published`, or `archived` |
| `page_css_class` | Optional CSS class applied to the page container |
| `published_at` | Automatically set when status changes to `published` |

**Route validation**: Route segments must contain only alphanumeric characters, hyphens, and underscores. Multi-segment routes (e.g., `about/team`) are supported.

### Content blocks

Each page contains ordered `CMSBlock` records. Each block has:

| Field | Purpose |
|-------|---------|
| `block_type` | Type identifier (e.g., `hero`, `text`, `image`, `cta`, `cards`) |
| `data` | JSON object conforming to the block type's schema |
| `order` | Display position within the page |

Block data is validated by `validate_block_data()` against type-specific JSON schemas.

### Publishing workflow

1. Create a page in Django admin with status `draft`
2. Add content blocks in the desired order
3. Use **live preview** to see the page as it will appear on the frontend
4. Change status to `published` — this sets `published_at` and makes the page accessible via the API
5. To take a page offline, change status to `archived`

### Live preview

The admin provides an iframe-based live preview:
- `GET /cms/live-preview/{page_id}/` — returns page data for the preview iframe (staff only)
- Preview tokens can be generated for sharing draft previews with non-staff users

### Frontend rendering

The React frontend's catch-all route (`*`) loads `CMSPageComponent`:
1. Extracts the current URL path
2. Calls `GET /cms/pages/{path}/`
3. Renders each block by type using component mapping

CMS-specific styles live in `pages/src/components/CMS/styles/` and `pages/src/components/CMS/page-styles/`.

## News articles

### Sync from RSS feeds

News articles are imported from external RSS feeds, not created manually in admin.

**Models:**
- `NewsFeedSource` — RSS feed URL and sync configuration
- `NewsArticle` — Imported article with title, content, source, and published date
- `NewsSyncLog` — Tracks each sync attempt with success/failure status

**Sync command:**
```bash
cd src && python manage.py sync_news --settings=core.settings.dev
```

**Admin workflow:**
1. Configure feed sources in Django admin → CMS → News Feed Sources
2. Run `sync_news` command (manually or via cron)
3. Review imported articles in Django admin → CMS → News Articles
4. Articles appear automatically on the `/news` frontend route

## Site settings

`SiteSettings` is a singleton model managing global configuration:

| Field | Purpose |
|-------|---------|
| `homepage_route` | Which CMS page route to use as the homepage |
| Site title, logo | Branding elements |
| Other global config | As needed |

The frontend's `HomepageResolver` reads `homepage_route` from the layout API to determine which page to load at `/`.

## Menus and footer

### Menu

The `Menu` model defines navigation structure. Menus are organized by type (header, footer) with ordered links.

### FooterContent

Customizable HTML content for the site footer. Loaded as part of the layout API response.

### Layout API

`GET /layout/` returns menus, footer, and homepage route in a single response. The frontend's `LayoutProvider` caches this in `sessionStorage` and revalidates periodically.

## Media assets

`CMSAsset` stores uploaded files (images, PDFs) for use in CMS blocks. In production, files are stored on S3; locally, they use the filesystem.

CKEditor 5 handles inline rich text uploads within block content, with uploads restricted to staff users.

## Related pages

- [Django Admin](django-admin.md) — Admin interface customization
- [API: CMS & News](../api/cms-and-news.md) — CMS and news endpoints
- [Architecture: Frontend](../architecture/frontend.md) — Frontend CMS rendering
- [Operations](operations.md) — Content maintenance tasks
