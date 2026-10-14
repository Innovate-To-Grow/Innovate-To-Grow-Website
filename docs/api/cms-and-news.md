# CMS & News API

Content management pages, news articles, page view analytics, and layout data.

## Overview

The CMS serves dynamic pages built from ordered content blocks. News articles are synced from external RSS feeds. The layout endpoint provides menu and footer data shared across all three React roots.

## Code locations

| Concern | Path |
|---------|------|
| CMS views | `src/apps/cms/views/` |
| CMS models | `src/apps/cms/models/` |
| CMS serializers | `src/apps/cms/serializers/` |
| CMS URLs | `src/apps/cms/cms_urls.py` |
| News URLs | `src/apps/cms/news_urls.py` |
| Analytics URLs | `src/apps/cms/analytics_urls.py` |
| Layout view | `src/apps/core/urls.py` (inline) or `src/apps/cms/views/` |

## CMS pages

### `GET /cms/pages/{route}/`

Fetches a published CMS page by its route path. The route can be multi-segment (e.g., `about/team`).

**Permission:** AllowAny

**Published page response:**
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

If the requested path is an active legacy route, the same endpoint returns a
permanent internal mapping instead of page content:

```json
{
  "redirect_to": "/new-path",
  "permanent": true
}
```

The React client follows this response with `location.replace()`, preserving
the browser's original query string and fragment. `?preview=true` bypasses
route redirects so editors are never navigated away from preview mode. At the
edge, the same active mappings are published as HTTP 301 rules when Amplify
synchronization is configured.

**Block types:** `hero`, `text`, `image`, `cta`, `cards`, `testimonials`, and others. Each type has a JSON schema defining its `data` structure, validated by `validate_block_data()`.

**Frontend rendering:** The catch-all route (`*`) in the React router renders `CMSPageComponent`, which fetches the page by the current URL path and renders each block by type.

### `GET /cms/live-preview/{page_id}/`

Returns the short-lived cached editor payload to the live-preview iframe.
Reading an existing cached payload is anonymous. When the cache is empty, only
a user with CMS app access may fall back to the current database page;
anonymous cache misses return 404, so draft database content is not exposed.

`POST` to the same endpoint replaces the cached editor payload and requires CMS
app access.

### `GET /cms/preview/{token}/`

Fetches a page preview using a time-limited token. Allows non-staff users to preview draft pages via a shared link.

### `GET /cms/embed-hosts/`

Public, cacheable iframe-host policy used by `SafeHtml`. Returns active exact or
wildcard host patterns plus a `revision`; the same revision is sent as the
`ETag`, and `If-None-Match` may receive 304. Until this policy has loaded, the
frontend strips every iframe.

### `GET /cms/embed/{slug}/`

Public payload for a `CMSEmbedWidget`, rendered by the SPA at `/_embed/{slug}` inside an iframe (CORS `*`,
`X-Frame-Options` exempt). `widget_type` is `blocks` (a subset of a published page's blocks plus `page_css`) or
`app_route` (an interactive route such as `/schedule`). For `/schedule` widgets the payload includes
`schedule_id` — the widget's default `CurrentProjectSchedule`, or `null` for the active schedule. A CMS
`embed_widget` block can override it per block by adding `?schedule_id=<uuid>` to the iframe URL; the SPA
prefers that query value over the payload's `schedule_id`, then falls back to the active schedule. Hidden
sections travel the same way (`hidden_sections` in the payload, `?hide-sections=` on the URL).

## Key CMS models

| Model | Purpose |
|-------|---------|
| `CMSPage` | Route-addressable page with status (draft, published, archived) |
| `RouteRedirect` | Immutable legacy source path mapped to a published internal destination |
| `CMSBlock` | Ordered content block within a page (JSON data by type) |
| `CMSEmbedWidget` | Iframe-embeddable widget: page blocks or an app route, with an optional default schedule |
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
cd src && python manage.py sync_news --settings=config.settings.local
```

**Models:**
- `NewsFeedSource` — RSS feed URL and update frequency
- `NewsArticle` — Imported article with title, content, source, published date
- `NewsSyncLog` — Tracks sync timestamps and errors

Feed sources are configured in Django admin.

RSS bodies are streamed with a 2 MiB limit and article bodies with a 5 MiB
limit. Oversized upstream responses fail explicitly and are not parsed.

## Analytics

### `POST /analytics/pageview/`

Tracks a page view. Called by the frontend's `trackPageView()` function.

**Request:**
```json
{
  "path": "/about",
  "referrer": "https://google.com",
  "visitor_id": "0b6a2f0e-6c1d-4c0e-9f8e-2f6f3a1d9b77"
}
```

`visitor_id` is optional: a random id the browser keeps in `localStorage` (a UUID, or any 1-64 characters of
`A-Z a-z 0-9 _ -`). A missing or malformed id never fails the request; the view is recorded without one. The user
agent and client IP are read from the request, not the body.

**Permission:** AllowAny

**Responses:** `201` with an empty body; `400` for a missing, empty or over-long `path` / `referrer`; `429` when a
limit below is reached. The frontend ignores every outcome, so a refused page view costs one analytics row and
nothing the visitor can see.

**Limits:** never per client IP (campus visitors share one).

| Limit | Rate | Key |
|-------|------|-----|
| `PageViewVisitorThrottle` | 120/minute | the `visitor_id` |
| `PageViewLegacyThrottle` | 600/minute | one shared bucket for requests without a usable id (older cached frontend bundles) |
| `PageViewTotalThrottle` | 3,000/minute | one constant key: all page views together |

- The per-visitor id is client-chosen, so the first two only stop a runaway client: a script can send a fresh id
  with every request. The total cap is what bounds such a flood. It is about twenty times the estimated busiest
  campus minute (150 page views); above it page views are answered `429` and not recorded, and the worker logs
  `analytics.pageview_total_cap` (WARNING) at most once a minute.
- The total counts only page views the per-visitor / legacy limit accepted, so one looping browser uses 120 of the
  3,000, not all of them. While the cap is reached, a request is refused before its id gets a bucket of its own.
- All three keep their history in the `throttle` cache alias, a bounded in-process `LocMemCache` (50,000 entries,
  least recently used culled first), never in the default cache. In production the default cache is a
  per-container file cache where every key is a file and every write lists the directory, so client-minted keys
  must not reach it (see [Environments](../deployment/environments.md#the-throttle-cache-alias)).
- In-process means per Uvicorn worker: with `WEB_CONCURRENCY=2` a container admits up to twice each rate, each ECS
  task has its own counters, and a restart forgets them. These are fairness limits over analytics rows; nothing
  about security or money depends on them.
- A flood from one off-campus address belongs at the edge:
  [WAF rate limits](../deployment/waf-rate-limits.md), pattern set C.

**Stored fields:** every field is bounded before it is buffered, because a batch is written with one
`bulk_create` and a value PostgreSQL refuses would lose the whole batch.

| Field | Bound |
|-------|-------|
| `path`, `referrer` | 2,048 characters each (the column size); longer values are rejected with `400` |
| `path`, in bytes | cut to 2,048 bytes of UTF-8. The column is indexed and PostgreSQL refuses an index entry over about 2,700 bytes. Real paths are percent-encoded ASCII, so this only affects a path of raw non-ASCII text |
| User agent | cut to 512 characters |
| Session key | the session cookie value when it is at most 64 characters, else empty |
| Client IP | stored when it parses as an IPv4 / IPv6 address, else `NULL` |
| `visitor_id` | 1-64 characters of the alphabet above, else `NULL` |

**Model:** `PageView` — stores timestamp, path, referrer, user agent, client IP and `visitor_id`. Writes are
buffered for performance. `visitor_id` is a nullable column without an index (nothing filters on it). The table
has no retention. The admin dashboard counts unique visitors by `visitor_id`, falling back to the IP address for
rows recorded without one.

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
