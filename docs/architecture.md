# System Architecture

This document describes the high-level architecture of the Innovate To Grow (I2G) website, covering both the Django backend and the React frontend.

## High-Level Overview

```
Browser
  │
  ├── Static assets ──▶ CloudFront CDN ──▶ S3 (static/ & media/)
  │
  └── API requests ───▶ CloudFront ──▶ ALB ──▶ ECS Fargate (Django + Gunicorn)
                                                     │
                                                     ├── PostgreSQL (RDS)
                                                     ├── Redis (ElastiCache, optional)
                                                     └── S3 (file storage)

Frontend (React SPA) ──▶ AWS Amplify
```

- **Frontend**: React SPA hosted on AWS Amplify, served from its own domain.
- **Backend**: Django REST API running on ECS Fargate behind an ALB, fronted by CloudFront.
- **Database**: PostgreSQL on RDS (SSL required). SQLite used in development.
- **Cache**: Redis via ElastiCache in production, falls back to in-memory `LocMemCache`.
- **Storage**: S3 for media uploads and collected static files in production, local filesystem in development.

## Backend Architecture

### Django Apps

The backend is organized into 6 Django apps plus the `core` project package:

| App | Purpose | Key Models |
|-----|---------|------------|
| **core** | Project configuration, base models, middleware, health check | `ProjectControlModel`, `ModelVersion` |
| **authn** | Authentication, member management | `Member` (custom user model), `I2GMemberGroup` |
| **pages** | CMS pages, components, forms, media, layout | `Page`, `HomePage`, `PageComponent`, `UniformForm`, `FormSubmission`, `Menu`, `FooterContent`, `MediaAsset`, `GoogleSheet` |
| **events** | Event management, Google Sheets sync, registration | `Event`, `Program`, `Track`, `Presentation`, `TrackWinner`, `SpecialAward`, `EventRegistration` |
| **notify** | Email/SMS verification, broadcast messaging | `GoogleGmailAccount`, `EmailMessageLayout`, `EmailLayout`, `BroadcastMessage` |
| **mobileid** | Mobile ID cards, barcodes, transactions | `Barcode`, `MobileID`, `Transaction` |

### Inter-App Dependencies

```
core ◀── authn ◀── pages
  ▲         ▲         ▲
  │         │         │
  ├── events (uses authn for registration)
  ├── notify (sends emails for authn verification, event registration)
  └── mobileid (uses authn Member model)
```

- All apps inherit from `core.models.ProjectControlModel`.
- `authn.Member` is the `AUTH_USER_MODEL` used project-wide.
- `notify` provides verification code/link services consumed by other apps.

### Base Model: ProjectControlModel

Defined in `src/core/models/base/control.py`, this abstract model provides shared infrastructure for all domain models:

- **UUID primary key** (`id` field, auto-generated `uuid4`)
- **Timestamps**: `created_at` (auto), `updated_at` (auto)
- **Soft delete**: `is_deleted` / `deleted_at` fields; `delete()` marks rather than removes
- **Versioning**: `version` counter, `save_version()`, `rollback()`, `get_version_diff()`
- **Managers**:
  - `objects` — `ProjectControlManager`, excludes soft-deleted records by default
  - `all_objects` — `AllObjectsManager`, includes everything

### Authentication

- Custom user model: `authn.Member` (uses `member_uuid` as the JWT claim)
- Backend: `EmailOrUsernameBackend` allows login by either email or username
- Passwords: RSA-encrypted on the client before transmission (see [Frontend Auth Flow](#authentication-flow))
- Tokens: JWT via `djangorestframework-simplejwt`
  - Access token lifetime: 1 hour
  - Refresh token lifetime: 7 days
  - Refresh rotation enabled

### URL Routing

All API routes are defined in `src/core/urls.py` and delegated to app-level `urls.py` files:

| Prefix | Target |
|--------|--------|
| `/health/` | Health check endpoint |
| `/admin/` | Django admin (Unfold theme) |
| `/authn/` | Auth endpoints |
| `/pages/` | CMS page endpoints |
| `/layout/` | Layout data (menus + footer) |
| `/events/` | Event endpoints |
| `/notify/` | Notification endpoints |
| `/mobileid/` | Mobile ID ViewSets |
| `/membership/` | Legacy event registration routes |

See [API Reference](api-reference.md) for the full endpoint list.

## Frontend Architecture

### Tech Stack

- **React 18** with TypeScript
- **React Router** for client-side routing
- **Axios** for API calls
- **Vite** for build tooling and dev server

### Multi-Root Mounting

The frontend mounts three independent React roots from `pages/src/main.tsx`:

| Root Element | Components | Providers |
|-------------|------------|-----------|
| `#root` | `RouterProvider`, `AuthModal`, `ProfileModal` | `HealthCheckProvider`, `AuthProvider` |
| `#menu-root` | `MainMenu` | `AuthProvider`, `LayoutProvider` |
| `#footer-root` | `Footer` | `LayoutProvider` |

Each root has its own React tree. Cross-root communication uses `window` custom events:

- `i2g-auth-state-change` — Syncs auth state (login/logout) across roots
- `i2g-auth-modal` — Opens/closes auth modals from any root (e.g., menu login button)
- `storage` event listener — Cross-tab sync via localStorage

### React Contexts

| Context | Purpose |
|---------|---------|
| `AuthProvider` | User state, login/register/logout actions, modal control |
| `LayoutProvider` | Menu and footer data from `/layout/` endpoint |
| `HealthCheckProvider` | Polls `/health/` every 10s, shows maintenance mode overlay |

### API Client

Defined in `pages/src/services/api/client.ts`:

- Base URL: `VITE_API_BASE_URL` env var, defaults to `/api`
- In development, Vite proxies `/api/*` to the Django backend (stripping the `/api` prefix)
- In production, `VITE_API_BASE_URL` points to the backend's CloudFront URL

### Vite Dev Proxy

Configured in `pages/vite.config.ts`, the dev server proxies these paths to `VITE_BACKEND_URL` (default `http://localhost:8000`):

| Path | Behavior |
|------|----------|
| `/api/*` | Strips `/api` prefix, forwards to Django |
| `/media/*` | Passed through directly |
| `/admin/*` | Passed through directly |
| `/static/*` | Passed through directly |

### Authentication Flow

1. Client fetches the RSA public key from `GET /api/authn/public-key/` (cached 5 minutes)
2. Password is encrypted client-side using Web Crypto API (`RSA-OAEP` + `SHA-256`)
3. Encrypted password (base64) + `key_id` sent to `POST /api/authn/login/` or `/register/`
4. Server decrypts with the corresponding private key, validates credentials, returns JWT tokens
5. Access token stored in memory, refresh token in localStorage
6. Axios interceptor auto-refreshes expired access tokens using the refresh endpoint

### Component Rendering Pipeline

Pages are rendered through a pipeline in `pages/src/components/PageContent/`:

```
Route ──▶ PageContent
            │
            ├── Fetches page data from /api/pages/<slug>/
            │
            └── ComponentListRenderer
                  │
                  ├── Filters: is_enabled === true
                  ├── Sorts: by order ascending
                  │
                  └── ComponentRenderer (per component)
                        │
                        ├── html → renders dangerouslySetInnerHTML
                        ├── markdown → rendered as HTML
                        ├── google_sheet → GoogleSheetTable component
                        ├── form → embedded UniformForm
                        │
                        ├── CSS Scoping:
                        │   Rules prefixed with .component-{id} selector
                        │   @-rules (media queries, keyframes) left unscoped
                        │
                        └── JS Sandboxing:
                            Executed in hidden <iframe sandbox="allow-scripts">
                            Communication via postMessage()
```

**CSS Scoping**: Each component's CSS is automatically scoped to `.component-{componentId}` to prevent style leakage between components. `@`-rules like `@media` and `@keyframes` are left unscoped.

**JS Sandboxing**: JavaScript code runs inside a sandboxed iframe with only `allow-scripts` permission. The script executes as an IIFE with a `root` parameter. Results and errors are communicated back via `postMessage()`.

## Caching Strategy

| What | TTL | Backend |
|------|-----|---------|
| Page data | 5 min | Django cache (Redis or LocMemCache) |
| HomePage (active) | 5 min | Django cache |
| Footer content | 5 min | Django cache |
| Layout (menus + footer) | 5 min | Django cache |
| Google Sheets data | Configurable per sheet (default 300s) | Django cache |
| RSA public key | 5 min | Client-side (in-memory) |

Cache is invalidated on model save via signals in the respective apps.
