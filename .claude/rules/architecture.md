# Architecture Notes

## Backend

- Django apps stay isolated by domain under `src/`.
- Thin entrypoints should delegate to services, serializers, admin helpers, or models.
- `config/settings/*.py` remain stable import targets even when implementation moves to submodules.
- Settings are modular: `config/settings/base.py` wildcard-imports `config/settings/components/` in order (framework/environment → framework/django → integrations/admin → integrations/api → integrations/editor). The environment entrypoints extend `base.py`: `local.py` (dev/SQLite), `test.py` (CI/PostgreSQL), and `production.py` (which also layers `components/production.py`). `_legacy_imports.py` is a meta-path shim that aliases pre-refactor top-level app imports (e.g. `event.models…`) to `apps.*` so landed migrations stay importable — which is why those migrations must never be edited.
- Main URL router: `config/urls.py` delegates to each app's `urls.py` (`ROOT_URLCONF = "config.urls"`).

### Django apps

| App | Purpose |
|-----|---------|
| `authn` | Auth, Member model, registration, login, JWT, admin invitations |
| `core` | Base models, middleware, management commands, shared utilities, service credential configs |
| `cms` | CMS pages and blocks, menus, footer, site settings, media, page view analytics, news articles and feed sync |
| `projects` | Projects, semesters, past project shares |
| `event` | Events, tickets, questions, registrations |
| `mail` | Email/SMS campaigns, recipient logs, magic login links, Gmail import, inbox with scam detection, SES event webhooks, unsubscribe management |
| `system_intelligence` | AI chat conversations, action requests, config, and data export |
| `common` | Shared cross-app infrastructure introduced by the apps/ refactor |
| `cli_admin` | OAuth2 + PKCE `/admin-api/` backing the `i2g-admin` CLI (generic record CRUD; see the `cli-admin` skill) |

### Base model: `ProjectControlModel`

Nearly all models inherit from `apps.core.models.ProjectControlModel`, defined in `apps/core/models/base/control.py`. It provides exactly two things:
- **UUID primary key** (not auto-increment integers)
- **Timestamps**: `created_at`, `updated_at` (both `db_index=True`)

There is **no soft delete and no version tracking** — deletes are hard deletes, and `objects` is a plain manager (no `all_objects`, `is_deleted`, `save_version`, or `ModelVersion`). For extra behavior, compose the mixins in `apps.core.models.mixins`: `AuthoredModel` (`created_by`/`updated_by`), `OrderedModel` (`order`), `ActiveModel` (`is_active`).

### Auth system

- JWT via `rest_framework_simplejwt` (access 1h, refresh 7d, rotation + blacklist).
- `Member` extends `AbstractUser` + `ProjectControlModel` — the PK (`id`) is a UUID.
- `EmailAuthBackend` (`apps.authn.backends`, the sole `AUTHENTICATION_BACKENDS` entry) authenticates by **verified `ContactEmail`** only — there is no username login path.
- Admin login is overridden: `apps.authn.views.AdminLoginView` at `/admin/login/`.
- Do NOT set `DEFAULT_THROTTLE_CLASSES` globally — it breaks tests at 127.0.0.1.

### URL routing

Root router in `config/urls.py`:
- `/admin/` — Unfold-themed admin (custom login at `/admin/login/`)
- `/authn/` — authentication endpoints
- `/cms/` — CMS API
- `/event/` — event endpoints
- `/news/` — news API (routed to `apps.cms.news_urls`)
- `/projects/` — project endpoints
- `/analytics/` — page view analytics (routed to `apps.cms.analytics_urls`)
- `/mail/` — magic login, unsubscribe/resubscribe, SES event webhook
- `/layout/` — combined menu + footer API (+ `/layout/styles.css`)
- `/admin-api/` — OAuth2 + PKCE generic record CRUD for the `i2g-admin` CLI (`apps.cli_admin`)
- `/livez/`, `/readyz/`, `/health/` — health probes intercepted by middleware (return JSON; `/livez/` skips the DB, `/readyz/` + `/health/` check it)
- `/maintenance/bypass/` — maintenance mode toggle
- `/csp-report/` — CSP violation report sink
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

- `HealthCheckMiddleware` intercepts `/livez/`, `/readyz/`, and `/health/` before other middleware; returns JSON with database + maintenance status (`/livez/` is always 200 and DB-free; `/readyz/` returns 503 when the DB is unavailable).
- `SiteMaintenanceControl` model drives maintenance mode.

## Frontend

- The frontend uses a feature-based (vertical-slice) layout under `pages/src/`:
  - `app/` owns bootstrap and app-shell infra: `providers.tsx` (the imperative 3-root mount, called from `main.tsx`), `router.tsx`, `HomepageResolver.tsx`, `ErrorBoundary/`, `MaintenanceMode/`.
  - `features/<domain>/` owns each domain (auth, cms, events, layout, news, projects) as a self-contained slice: `api/` (data layer), `components/` (UI), optional `hooks/`, a `types.ts`, and a public `index.ts` barrel. The six features import from each other only through those barrels.
  - `routes/` owns routed page components (NewsPage, ProjectsPage, etc.), lazy-loaded by `app/router.tsx` via deep imports (importing through a barrel would defeat code-splitting).
  - `lib/` owns framework-agnostic utilities: `api-client.ts` (shared Axios client), `crypto.ts`, `time.ts`, `semester.ts`, `safeHref.ts`, `phoneRegions.ts`, `analytics.ts`, `health.ts`.
  - `components/ui/` owns cross-feature presentational components (`SafeHtml/`, `SheetsDataTable/`).
  - `hooks/` owns cross-feature hooks (e.g. `usePageTracking`); `types/` owns shared types (`api.ts` → `PaginatedResponse`); `assets/styles/` owns global styles (`index.css` stays at `src/` root).
- A `@/*` path alias maps to `pages/src/*` (configured in `tsconfig.app.json`, `vite.config.ts`, and `vitest.config.ts`). Prefer `@/...` imports over deep relative paths.
- Add new endpoints to the matching feature's `api/` module (or `lib/api-client.ts` for the shared client), not a central dumping-ground service module.
- Within a feature, import the data layer via the `api/` sub-path (e.g. `@/features/auth/api`) rather than the feature barrel, to keep barrels acyclic.
- Three React roots: `#root` (main app with router), `#menu-root` (MainMenu only, no BrowserRouter), `#footer-root` (Footer). This means menu and footer render independently and share auth state via the `i2g-auth-state-change` custom event.
- Vite dev server proxies `/api`, `/media`, `/static` to Django backend (configurable via `VITE_BACKEND_URL` env var, defaults to `http://127.0.0.1:8000`). The `/api` proxy **strips the prefix** — frontend calls `/api/cms/pages/` which Vite rewrites to `/cms/pages/` for Django.
- Manual code-splitting: react-vendor and router chunks are split separately in `vite.config.ts`.
- Testing: vitest + @testing-library/react.

## Admin theme

- Unfold admin with custom OKLch color palette (purple primary).
- All admin classes must inherit from `apps.core.admin.BaseModelAdmin` (or `ReadOnlyModelAdmin`), not Django's stock `ModelAdmin`.
- Sidebar organized into 5 sections: Site Settings, CMS, Events, Projects, Members & Auth.
- Tab groups for domain-related models configured in `config/settings/components/integrations/admin.py`.

## CI/CD

GitHub Actions workflows under `.github/workflows/`:

| Workflow | Triggers | Purpose |
|---|---|---|
| `ci.yml` | push / PR (paths) | Secrets scan (gitleaks), Ruff lint+format, Bandit, Django tests on PostgreSQL (`config.settings.test`), migration validation, frontend lint + type check + vitest + build |
| `lint.yml` | push / PR | Standalone lint pass |
| `codeql.yml` | push / PR + Mon 03:00 UTC | CodeQL Python + JS/TS analysis |
| `claude-code-review.yml` | `workflow_run` after CI success | Automated Claude PR review (gated on green CI) |
| `claude.yml` | issue / PR comments mentioning `@claude` | On-demand Claude reviews |
| `deploy-backend.yml` | `workflow_run` after CI on main | Build → ECR → ECS deploy (Uvicorn) |
| `deploy-frontend.yml` | after CI on main | Build → S3 ZIP → Amplify deploy |

Notes:
- `claude-code-review.yml` reads from the **default branch** (per `workflow_run`); edits only take effect after merge to main.
- `deploy-*` workflows gate on `github.event.workflow_run.conclusion == 'success'`.
- Backend Docker image: Python 3.11-slim, served by Uvicorn over ASGI (`config.asgi:application`) via `src/entrypoint.sh`: `--workers ${WEB_CONCURRENCY:-2}`, `--timeout-graceful-shutdown 120`, `--limit-concurrency 20`, port 8000. (gunicorn is still a dependency but is not the runtime server.)

## Product behavior to preserve

- Public routes and API paths stay stable.
- CMS pages still resolve by route.
- Auth state continues syncing across React roots with the `i2g-auth-state-change` event.

## Docs

Detailed architecture, API, CMS, deployment, and integration docs live in `docs/`.
