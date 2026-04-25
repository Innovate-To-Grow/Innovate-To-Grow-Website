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
| `mail` | Email campaigns, recipient logs, magic login links, Gmail import |
| `news` | Articles, feed sources, sync from external feeds |
| `sponsors` | Sponsor management |

### Base model: `ProjectControlModel`

Nearly all models inherit from `core.models.ProjectControlModel`, which provides:
- **UUID primary key** (not auto-increment integers)
- **Timestamps**: `created_at`, `updated_at`
- **Soft delete**: `is_deleted`, `deleted_at`; `objects` excludes deleted, `all_objects` includes all
- **Version tracking**: JSON snapshots via `save_version()`, `rollback()`, `get_versions()`; stored in `core.models.ModelVersion` (generic FK by content type + object UUID)

### Auth system

- JWT via `rest_framework_simplejwt` (access 1h, refresh 7d, rotation + blacklist).
- `Member` extends `AbstractUser` + `ProjectControlModel` — the PK (`id`) is a UUID.
- `EmailOrUsernameBackend` allows login by username or verified email.
- Admin login is overridden: `authn.views.AdminLoginView` at `/admin/login/`.
- Do NOT set `DEFAULT_THROTTLE_CLASSES` globally — it breaks tests at 127.0.0.1.

### URL routing

Root router in `core/urls.py`:
- `/admin/` — Unfold-themed admin (custom login at `/admin/login/`)
- `/authn/` — authentication endpoints
- `/cms/` — CMS API
- `/event/` — event endpoints
- `/news/` — news API (routed to `cms.news_urls`)
- `/projects/` — project endpoints
- `/sponsors/` — sponsor endpoints
- `/analytics/` — page view analytics (routed to `cms.analytics_urls`)
- `/layout/` — combined menu + footer API
- `/health/` — ALB health check (intercepted by middleware, returns JSON status)
- `/maintenance/bypass/` — maintenance mode toggle
- `/ckeditor5/` — rich text editor uploads

### Settings differences

| | Dev | CI | Prod |
|---|---|---|---|
| Database | SQLite | PostgreSQL (GH Actions service) | PostgreSQL + SSL |
| Cache | Local memory | Local memory | Redis (file-based fallback) |
| Email | Console backend | Console backend | SMTP |
| Storage | Local filesystem | Local filesystem | S3/R2 via boto3 |
| Passwords | Plain text OK | Plain text OK | Encrypted required |

### Middleware

- `HealthCheckMiddleware` intercepts `/health/` before other middleware; returns JSON with database + maintenance status (always 200 for ALB probes).
- `SiteMaintenanceControl` model drives maintenance mode.

## Frontend

- `app/` owns bootstrap and router setup.
- `pages/` (within `src/`) owns routed page components (HomePage, NewsPage, etc.).
- `features/` owns domain code such as auth, CMS, layout, projects, events, and news.
- `shared/` owns reusable auth helpers, API clients, hooks, styles, and utilities.
- `pages/src/services/` houses cross-cutting helpers (`auth.ts`, `crypto.ts`) and a `services/api/` subdirectory of feature-specific API modules. Add new endpoints to the matching `services/api/<feature>.ts`, not a single mega-module.
- Three React roots: `#root` (main app with router), `#menu-root` (MainMenu only, no BrowserRouter), `#footer-root` (Footer). This means menu and footer render independently and share auth state via the `i2g-auth-state-change` custom event.
- Vite dev server proxies `/api`, `/media`, `/static` to Django backend (configurable via `VITE_BACKEND_URL` env var, defaults to `http://localhost:8000`).
- Manual code-splitting: react-vendor and router chunks are split separately in `vite.config.ts`.
- Testing: vitest + @testing-library/react.

## Admin theme

- Unfold admin with custom OKLch color palette (purple primary).
- All admin classes must inherit from `core.admin.BaseModelAdmin` (or `ReadOnlyModelAdmin`), not Django's stock `ModelAdmin`.
- Sidebar organized into 5 sections: Site Settings, CMS, Events, Projects, Members & Auth.
- Tab groups for domain-related models configured in `core/settings/components/integrations/admin.py`.

## CI/CD

GitHub Actions workflows under `.github/workflows/`:

| Workflow | Triggers | Purpose |
|---|---|---|
| `ci.yml` | push / PR (paths) | Secrets scan (gitleaks), Ruff lint+format, Django tests on SQLite, PostgreSQL migration validation, frontend lint + type check + vitest + build |
| `lint.yml` | push / PR | Standalone lint pass |
| `codeql.yml` | push / PR + Mon 03:00 UTC | CodeQL Python + JS/TS analysis |
| `claude-code-review.yml` | `workflow_run` after CI success | Automated Claude PR review (gated on green CI) |
| `claude.yml` | issue / PR comments mentioning `@claude` | On-demand Claude reviews |
| `deploy-backend.yml` | `workflow_run` after CI on main | Build → ECR → ECS deploy (Gunicorn) |
| `deploy-frontend.yml` | after CI on main | Build → S3 ZIP → Amplify deploy |

Notes:
- `claude-code-review.yml` reads from the **default branch** (per `workflow_run`); edits only take effect after merge to main.
- `deploy-*` workflows gate on `github.event.workflow_run.conclusion == 'success'`.
- Backend Docker image: Python 3.11-slim + Gunicorn (3 workers, 120s timeout, port 8000).

## Product behavior to preserve

- Public routes and API paths stay stable.
- CMS pages still resolve by route.
- Auth state continues syncing across React roots with the `i2g-auth-state-change` event.

## Docs

Detailed architecture, API, CMS, deployment, and integration docs live in `docs/`.
