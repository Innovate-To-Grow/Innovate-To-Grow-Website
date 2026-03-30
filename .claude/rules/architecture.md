# Architecture Notes

## Backend

- Django apps stay isolated by domain under `src/`.
- Thin entrypoints should delegate to services, serializers, admin helpers, or models.
- `core/settings/*.py` remain stable import targets even when implementation moves to submodules.
- Settings are modular: `core/settings/base.py` wildcard-imports from `core/settings/components/` (framework/environment, framework/django, integrations/api, integrations/admin, integrations/editor, production). `dev.py`, `prod.py`, and `ci.py` extend `base.py`.
- Main URL router: `core/urls.py` delegates to each app's `urls.py`.

### Django apps

| App | Purpose |
|-----|---------|
| `authn` | Auth, Member model, registration, login, JWT, admin invitations |
| `core` | Base models, middleware, management commands, shared utilities |
| `cms` | CMS pages and blocks, menus, footer, site settings, media, page view analytics |
| `projects` | Projects, semesters, past project shares |
| `event` | Events, tickets, questions, registrations |
| `news` | Articles, feed sources, sync from external feeds |
| `sponsors` | Sponsor management |

### Base model: `ProjectControlModel`

Nearly all models inherit from `core.models.ProjectControlModel`, which provides:
- **UUID primary key** (not auto-increment integers)
- **Timestamps**: `created_at`, `updated_at`
- **Soft delete**: `is_deleted`, `deleted_at`; `objects` excludes deleted, `all_objects` includes all
- **Version tracking**: JSON snapshots via `save_version()`, `rollback()`, `get_versions()`

### Auth system

- JWT via `rest_framework_simplejwt` (access 1h, refresh 7d, rotation + blacklist).
- `Member` extends `AbstractUser` + `ProjectControlModel` — the PK (`id`) is a UUID.
- `EmailOrUsernameBackend` allows login by username or verified email.
- Do NOT set `DEFAULT_THROTTLE_CLASSES` globally — it breaks tests at 127.0.0.1.

## Frontend

- `app/` owns bootstrap and router setup.
- `pages/` (within `src/`) owns routed page components (HomePage, NewsPage, etc.).
- `features/` owns domain code such as auth, CMS, layout, projects, events, and news.
- `shared/` owns reusable auth helpers, API clients, hooks, styles, and utilities.
- `services/api/` houses feature-specific API service modules.
- Three React roots: `#root` (main app with router), `#menu-root` (MainMenu only, no BrowserRouter), `#footer-root` (Footer). This means menu and footer render independently and share auth state via the `i2g-auth-state-change` custom event.
- Vite dev server proxies `/api`, `/media`, `/static` to Django backend (configurable via `VITE_BACKEND_URL` env var, defaults to `http://localhost:8000`).

## Product behavior to preserve

- Public routes and API paths stay stable.
- CMS pages still resolve by route.
- Auth state continues syncing across React roots with the `i2g-auth-state-change` event.

## Docs

Detailed architecture, API, CMS, deployment, and integration docs live in `docs/`.
