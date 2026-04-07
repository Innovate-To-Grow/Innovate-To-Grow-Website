# CMS & News API

Content management pages, news articles, page view analytics, and layout data.

## Overview

The CMS serves dynamic pages built from ordered content blocks. News articles are synced from external RSS feeds. The layout endpoint provides menu and footer data shared across all three React roots.

## Code locations

| Concern | Path |
|---------|------|
| CMS views | `src/cms/views/` |
| CMS models | `src/cms/models/` |
| CMS serializers | `src/cms/serializers/` |
| CMS URLs | `src/cms/cms_urls.py` |
| News URLs | `src/cms/news_urls.py` |
| Analytics URLs | `src/cms/analytics_urls.py` |
| Layout view | `src/core/urls.py` (inline) or `src/cms/views/` |

## CMS pages

### `GET /cms/pages/{route}/`

Fetches a published CMS page by its route path. The route can be multi-segment (e.g., `about/team`).

**Permission:** AllowAny

**Response:**
```json
{
  "id": "<uuid>",
  "title": "About Us",
  "slug": "about-us",
  "route": "about",
  "meta_description": "...",
  "status": "published",
  "page_css_class": "about-page",
  "blocks": [
    {
      "id": "<uuid>",
      "block_type": "hero",
      "data": { "heading": "...", "image": "..." },
      "order": 0
    },
    {
      "id": "<uuid>",
      "block_type": "text",
      "data": { "content": "<html>..." },
      "order": 1
    }
  ]
}
```

**Block types:** `hero`, `text`, `image`, `cta`, `cards`, `testimonials`, and others. Each type has a JSON schema defining its `data` structure, validated by `validate_block_data()`.

**Frontend rendering:** The catch-all route (`*`) in the React router renders `CMSPageComponent`, which fetches the page by the current URL path and renders each block by type.

### `GET /cms/live-preview/{page_id}/`

Returns page data for the admin live preview iframe. Used by the Django admin CMS editor.

**Permission:** Staff only

### `GET /cms/preview/{token}/`

Fetches a page preview using a time-limited token. Allows non-staff users to preview draft pages via a shared link.

## Key CMS models

| Model | Purpose |
|-------|---------|
| `CMSPage` | Route-addressable page with status (draft, published, archived) |
| `CMSBlock` | Ordered content block within a page (JSON data by type) |
| `CMSAsset` | Uploaded media files (images, PDFs) |
| `SiteSettings` | Global settings including `homepage_route` |
| `Menu` | Navigation menu structure (header, footer) |
| `FooterContent` | Customizable footer HTML content |

**Route validation:** Route segments must be alphanumeric with hyphens and underscores only. The `route` field is unique.

**Status transitions:** `draft` → `published` sets `published_at` timestamp automatically.

## News

### `GET /news/`

Paginated list of published news articles, newest first.

**Permission:** AllowAny

**Serializer:** `NewsArticleSerializer`

### `GET /news/{id}/`

Single article detail.

**Permission:** AllowAny

### News sync

Articles are imported from RSS feeds via the `sync_news` management command:

```bash
cd src && python manage.py sync_news --settings=core.settings.dev
```

**Models:**
- `NewsFeedSource` — RSS feed URL and update frequency
- `NewsArticle` — Imported article with title, content, source, published date
- `NewsSyncLog` — Tracks sync timestamps and errors

Feed sources are configured in Django admin.

## Analytics

### `POST /analytics/pageview/`

Tracks a page view. Called by the frontend's `trackPageView()` function.

**Request:**
```json
{
  "route": "/about",
  "referrer": "https://google.com",
  "user_agent": "Mozilla/5.0..."
}
```

**Permission:** AllowAny

**Model:** `PageView` — stores timestamp, route, referrer, and user agent. Writes are buffered for performance.

## Layout

### `GET /layout/`

Returns combined menu and footer data. Consumed by all three React roots.

**Response:**
```json
{
  "menus": [...],
  "footer": { "content": "..." },
  "homepage_route": "home"
}
```

**Frontend caching:** `LayoutProvider` caches this in `sessionStorage` (versioned `v1` key), revalidating every 60 seconds or on window focus.

## Related pages

- [Architecture: Frontend](../architecture/frontend.md) — CMS page rendering and layout provider
- [Architecture: Request Flow](../architecture/request-flow.md) — CMS page resolution sequence
- [CMS & Admin: Content Management](../cms-admin/content-management.md) — Admin editing workflows
- [Routing Overview](routing-overview.md) — Full URL map
