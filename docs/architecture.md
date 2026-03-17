# System Architecture

## Overview

The Innovate to Grow (ITG) website is a full-stack web application for UC Merced's Innovate to Grow program. It consists of:

- **Backend**: Django 5.2 + Django REST Framework 3.16 (Python 3.11+)
- **Frontend**: React 19 + TypeScript 5.9 + Vite 7
- **Database**: SQLite (development), PostgreSQL (production)
- **Cache**: In-memory LocMemCache (development), Redis (production)
- **Storage**: Local filesystem (development), AWS S3 (production)
- **Email**: Gmail API (service account) and AWS SES

The backend serves a REST API consumed by the React single-page application. The Django admin interface provides content management.

## Backend App Map

All Django apps live under `src/`. Each app's models inherit from `ProjectControlModel` (see below) unless noted.

| App | Purpose |
|-----|---------|
| `core` | Project configuration, settings (base/dev/prod), health check middleware, `ProjectControlModel` base class, versioning system, `SiteMaintenanceControl` model |
| `pages` | Site layout (Menu, FooterContent, SiteSettings, GoogleSheetSource) and block-based CMS (CMSPage, CMSBlock). CMS pages have a route, status (draft/published/archived), and ordered content blocks. API at `/cms/pages/<route>/`, `/layout/`, `/sheets/<slug>/`. CMS tables use `cms_cmspage` / `cms_cmsblock` names for historical compatibility. |
| `authn` | Authentication: custom Member model, JWT tokens (SimpleJWT), RSA password encryption, email verification, contact emails/phones, password reset |
| `event` | Event management: Event, Ticket, Question models. Currently no public API endpoints (event data served via CMS and Google Sheets) |
| `news` | News articles: NewsArticle, NewsFeedSource, NewsSyncLog. RSS feed syncing via `sync_news` management command |
| `projects` | Semester and project management: Semester, Project. Google Sheets import via `sync_projects` management command |
| `mail` | Email sending: Gmail API (GoogleAccount, EmailLog) and AWS SES (SESAccount, SESEmailLog) with audit logging |

### URL Routing

All URL patterns are registered in `src/core/urls.py`:

| Prefix | Target |
|--------|--------|
| `/admin/` | Django admin (django-unfold themed) |
| `/layout/` | `LayoutAPIView` — menus, footer, site settings |
| `/sheets/` | `pages.urls` — Google Sheets data proxy |
| `/event/` | `event.urls` — (currently empty) |
| `/news/` | `news.urls` — news article list and detail |
| `/projects/` | `projects.urls` — current/past projects |
| `/cms/` | `pages.cms_urls` — CMS page retrieval and preview |
| `/authn/` | `authn.urls` — authentication endpoints |
| `/ckeditor5/` | CKEditor 5 upload endpoint |
| `/health/` | Health check (handled by middleware, bypasses ALLOWED_HOSTS) |

## ProjectControlModel

All major models inherit from `core.models.ProjectControlModel` (`src/core/models/base/control.py`), which provides:

- **UUID primary keys** — `id` is a UUIDField, not auto-incrementing
- **Soft delete** — `delete()` marks `is_deleted=True`; `hard_delete()` permanently removes; `restore()` undeletes
- **Version control** — `save_version()`, `get_versions()`, `rollback()`, `get_version_diff()`
- **Two managers** — `objects` (excludes soft-deleted) and `all_objects` (includes all)
- **Timestamps** — `created_at` (auto_now_add), `updated_at` (auto_now)

Version history is stored in the `ModelVersion` model using Django's ContentType framework.

## Frontend Architecture

The frontend lives in `pages/` and is built with Vite. Configuration is in `pages/vite.config.ts`.

### Three React Roots

The application renders into three separate React root elements defined in `pages/index.html`:

| Root | Element | Contents | Router |
|------|---------|----------|--------|
| `#root` | Main app | Full routing, all providers (HealthCheck, Auth, Layout) | BrowserRouter |
| `#menu-root` | Navigation | MainMenu component only | None (uses programmatic navigation) |
| `#footer-root` | Footer | Footer component only | None |

This split allows the menu and footer to render independently. Auth state is synchronized across roots via the `i2g-auth-state-change` window event and the `storage` event for cross-tab sync.

### Vite Proxy

During development, Vite proxies requests to the Django backend:

| Path | Target |
|------|--------|
| `/api/*` | `http://localhost:8000` (strips `/api` prefix) |
| `/media/*` | `http://localhost:8000` |
| `/admin/*` | `http://localhost:8000` |
| `/static/*` | `http://localhost:8000` |

### CMS Pages vs Data-Driven Pages

The frontend has two rendering paths:

**CMS-managed pages** use `CMSPageComponent` which fetches block-based content from `/cms/pages/<route>/` and renders it through `BlockRenderer`. These are content pages like `/about`, `/faqs`, `/contact-us`, `/privacy`, `/students`, `/judges`, `/sponsorship`, etc.

**Data-driven pages** have dedicated React components with their own API calls:

| Route | Component | Data Source |
|-------|-----------|-------------|
| `/news`, `/news/:id` | NewsPage, NewsDetailPage | `/news/` API |
| `/current-projects`, `/past-projects`, `/projects/:id` | ProjectsPage, PastProjectsPage, ProjectDetailPage | `/projects/` API |
| `/event`, `/schedule` | EventPage, SchedulePage | Google Sheets via `/sheets/current-event/` |
| `/events/:eventSlug` | EventArchivePage | Google Sheets via slug |
| `/projects-teams` | ProjectsTeamsPage | Google Sheets |
| `/acknowledgement` | AcknowledgementPage | Static/CMS |

The homepage route is dynamic — `HomepageResolver` reads `homepage_route` from the layout API and renders that CMS page at `/` without redirecting. Unmatched frontend routes fall through to CMS page lookup before showing a 404.

### API Services Layer

Frontend API calls are organized in `pages/src/services/api/`:

| Module | Purpose |
|--------|---------|
| `client.ts` | Axios instance configured with base URL and JSON headers |
| `layout.ts` | Layout data (menus, footer, site settings, prefetched sheets) |
| `cms.ts` | CMS page fetching and preview |
| `news.ts` | News list (paginated) and detail |
| `projects.ts` | Current/past projects and detail |
| `sheets.ts` | Google Sheets data by slug (with per-slug caching) |
| `health.ts` | Health check polling |

Authentication is in `pages/src/services/auth.ts` (Axios instance with JWT interceptor, auto-refresh on 401). Password encryption is in `pages/src/services/crypto.ts` (RSA-OAEP via Web Crypto API).

## Authentication

### Auth Flow

1. Client fetches RSA public key from `GET /authn/public-key/`
2. Client encrypts password using RSA-OAEP (Web Crypto API), base64-encodes it
3. Client sends email + encrypted password to `POST /authn/login/`
4. Server decrypts password with stored RSA private key
5. Server authenticates via Django's `authenticate()` with `EmailOrUsernameBackend`
6. Server returns JWT access + refresh tokens

### JWT Configuration

- `USER_ID_FIELD = "id"` — the UUID primary key on Member
- `USER_ID_CLAIM = "member_uuid"` — claim name in token payload
- Token blacklisting enabled via `rest_framework_simplejwt.token_blacklist`
- `BLACKLIST_AFTER_ROTATION = True`
- Access tokens are short-lived; refresh tokens are rotated on use

### Key Details

- `Member.member_uuid` is a Python `@property` alias for `id` — it is not a database column
- In production, `REQUIRE_ENCRYPTED_PASSWORDS = True` blocks plaintext password submission
- In development, `REQUIRE_ENCRYPTED_PASSWORDS = False` allows plaintext for testing
- `LoginRateThrottle` limits login attempts to 10/minute
- Default permission class is `IsAuthenticated` — public endpoints must explicitly set `AllowAny`

## Caching

### Strategy

| Cache Key Pattern | TTL | Content |
|-------------------|-----|---------|
| `layout:data` | 600s | Menus, footer, site settings, prefetched sheets |
| `cms:page:{route}` | 300s | Published CMS page with blocks |
| `cms:preview:{token}` | 600s | Preview page data (admin-generated) |
| `sheets:{slug}:data` | Configurable (default 300s) | Parsed Google Sheets data |
| `sheets:{slug}:stale` | 6x fresh TTL | Stale copy for background refresh |
| `projects:current` | 300s | Current semester projects |
| `layout.footer_content.active` | 300s | Active footer content |

### Invalidation

Signal handlers in `src/pages/signals.py` automatically clear relevant cache keys when models are saved or deleted:

- Menu, FooterContent, SiteSettings save/delete → clear `layout:data`
- GoogleSheetSource save/delete → clear `sheets:{slug}:data` and `sheets:{slug}:stale`
- CMSPage save/delete → clear `cms:page:{route}`
- CMSBlock save/delete → clear parent page's cache

### Google Sheets Caching

Google Sheets data uses a **stale-while-revalidate** strategy:

1. **Fresh cache hit** → return immediately
2. **Stale cache hit** → return stale data, trigger background refresh in a daemon thread
3. **Full miss** → synchronous fetch from Google Sheets API

This ensures users never experience a cold-cache delay during normal operation.

## Email

Two email providers are available, configured per-account in the admin:

| Provider | Service | Configuration |
|----------|---------|---------------|
| Gmail API | Google Workspace delegation | Service account JSON stored in `GoogleAccount` model |
| AWS SES | Amazon SES | Access key/secret in env vars or `SESAccount` model |

All sends are logged to `EmailLog` (Gmail) or `SESEmailLog` (SES) for audit. HTML content is sanitized with bleach before sending.

## Admin Interface

The admin uses **django-unfold** for theming and **CKEditor 5** for rich text editing.

Key admin features:
- **CMS block editor**: Visual drag-and-drop interface for managing page blocks (custom JavaScript in admin form template)
- **Menu editor**: Visual menu builder with app routes and CMS pages dropdown
- **Import/export**: CMS pages can be exported as JSON and imported via admin actions
- **Singleton patterns**: SiteSettings and FooterContent enforce single-active-record

## External Integrations

| Integration | Purpose | Auth Method |
|-------------|---------|-------------|
| Google Sheets API | Read project/event data for display | Service account JSON or API key |
| Gmail API | Send transactional/admin emails | Service account with domain-wide delegation |
| AWS SES | Send transactional emails (alternative to Gmail) | IAM access key |
| AWS S3 | Static and media file storage (production) | IAM access key or instance role |
| Redis | Cache backend (production) | Connection URL |
| RSS feeds | News article syncing | Public HTTP fetch |
