# Repository Structure

## Top-level layout

```
.
├── src/                    # Django backend (all Python code)
│   ├── apps/               # Django apps
│   │   ├── core/           # Framework, shared building blocks, middleware, durable jobs
│   │   ├── authn/          # Authentication, Member, contacts, invitations
│   │   ├── cms/            # CMS pages, news, analytics, menus, footer
│   │   ├── event/          # Registration, ticketing, schedule, check-in
│   │   ├── projects/       # Past projects, semesters, sharing
│   │   ├── mail/           # Campaigns, recipient logs, login links
│   │   ├── system_intelligence/  # Admin AI assistant (agents, actions, exports)
│   │   └── cli_admin/      # OAuth2 + PKCE CRUD API for the i2g-admin CLI
│   ├── config/             # Django settings, URLs, ASGI/WSGI
│   ├── assets/             # Pinned third-party static libs (vendor/), app-agnostic
│   ├── manage.py           # Django management entry point
│   ├── requirements/       # Inputs plus hashed local/production locks
│   ├── requirements.txt    # Hash-checked local/CI convenience include
│   ├── Dockerfile          # Production container image
│   └── .env                # Local environment variables (not in version control)
├── pages/                  # React frontend (TypeScript + Vite)
│   ├── src/                # Application source
│   ├── index.html          # HTML shell with independently mounted React roots
│   ├── package.json        # Node dependencies and scripts
│   ├── vite.config.ts      # Dev server proxy and build config
│   └── vitest.config.ts    # Test runner config
├── aws/                    # ECS task definition templates
├── scripts/ci/             # CI planners, validators, quality + dependency checks
├── docs/                   # Technical documentation (this directory)
├── archive/page/           # Standalone historical archive service
├── cli/                    # Standalone i2g-admin Python CLI
├── .github/workflows/      # CI/CD pipelines
├── pyproject.toml          # Ruff linter/formatter config
├── CONTRIBUTING.md         # Contributor guidelines
└── README.md               # Project overview with doc links
```

## Backend app layout

Each Django app under `src/` follows a consistent structure:

```
src/apps/<app>/
├── models/             # or models.py — domain models
├── views/              # or views.py — API views
├── serializers/        # or serializers.py — DRF serializers
├── services/           # Business logic modules
├── admin/              # or admin.py — Django admin configuration
├── urls.py             # App URL patterns
├── tests/              # Test modules
├── templates/          # Django templates (emails, admin overrides)
├── migrations/         # Database migrations
└── apps.py             # App configuration
```

Not every app has all directories — `system_intelligence/` has no public REST surface. A
directory is used only where there is more than one module to hold; single-module concerns
stay as plain `.py` files (for example `apps/core/renderers.py`, `apps/cms/signals.py`).

### A note on `apps/core`

`core` holds the framework primitives every other app builds on: `ProjectControlModel`,
the model mixins, reusable DRF utilities, `BaseModelAdmin`, `utils/access.py`, the
`middleware/` package, and the service-credential singletons. It also holds shared infrastructure
that names no business app:

| Subsystem | Path | Importing apps |
|---|---|---|
| Durable job queue | `core/services/background_jobs/` | `authn`, `cms`, `event`, `mail` (each registers its job kinds in `AppConfig.ready()`) |
| Read-only ORM sandbox | `core/services/db_tools/safe_orm/` | `cli_admin`, `system_intelligence` |
| AWS credentials + SNS SMS | `core/services/aws/` | `authn`, `event`, `mail` |
| Email delivery (MIME, SES/SMTP) | `core/services/email/` | `authn`, `event`, `mail` |

Domain subsystems that used to live here have moved to their owners. The Bedrock client is now
`system_intelligence/services/bedrock/`, the assistant's query tools are
`system_intelligence/services/query_tools/`, and the sitemap view is `cms/views/sitemap.py`.
`core` does not import business apps at module level, and
`scripts/ci/check_python_dependencies.py` enforces that. See
[Code Quality Rules](code-quality.md#dependency-directions) for the allowed direction of every app
and for the registration hooks.

`src/apps/core/services/__init__.py` carries the full subsystem map as a module docstring, so it
is visible from an editor without opening the docs.

Extracting `background_jobs` or `db_tools` into their own apps would need new Django app labels. That
is deferred: `apps/core/utils/access.py` and `Member.admin_apps` store app labels **in the
database** (a `JSONField` per admin user), so a new label needs a data migration to backfill existing
admins' grants, or they silently lose access.

### Splitting a module inside an app

A large module becomes a package that keeps the old import path as its public interface. Its
`__init__.py` re-exports what callers use, and the parts are named by responsibility. Examples:
`system_intelligence/services/public_assistant/budget/` (limits, usage, database store, cache
store), `mail/services/campaign/dispatch/` (launch, channels, email job, SMS job, job state,
failures), and `cms/services/amplify/` (rules, config, reconcile, jobs). Tests patch the submodule
that owns a name (for example `budget.cache_store._shared_redis_client`), not the package.

## Frontend source layout

```
pages/src/
├── main.tsx            # Entry point: mounts the independent React roots
├── app/                # Composition: providers/, router/ (routes + EMBED_APP_ROUTES), ErrorBoundary/,
│                       #   MaintenanceMode/, thirdPartyLoaders/
├── routes/             # Routed pages, lazy-loaded via deep imports; page-only hooks and sections
│                       #   live beside the page (e.g. EventRegistrationPage/registration/)
├── features/<domain>/  # assistant, auth, cms, events, layout, news, projects:
│                       #   api/, components/, optional hooks/, types.ts, public index.ts
├── components/         # Cross-feature UI (Icon, NotFoundPage, SafeHtml, SheetsDataTable, ...)
├── hooks/              # Cross-feature hooks (useCopyLink, usePageTitle, usePageTracking)
├── lib/                # Framework-agnostic: api/ (client, error messages, embed hosts), format/, security/
├── types/              # Shared API types
├── assets/             # Design tokens (tokens.css) and shared CSS
└── __tests__/          # Vitest tests, mirroring the source tree
```

Allowed imports between these layers are listed in
[Code Quality Rules](code-quality.md#frontend-layers) and checked by `npm run check:structure`.

## Configuration files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Ruff config: line length 120, Python 3.11, double quotes, LF endings |
| `src/.env` | Local env vars (SECRET_KEY, DB, AWS, Google Sheets) — not committed |
| `src/.env.example` | Template for `.env` with all expected variables |
| `pages/vite.config.ts` | Dev proxy to Django, manual code-splitting chunks |
| `pages/vitest.config.ts` | jsdom environment, 30s timeout |
| `pages/tsconfig.app.json` | ES2022 target, strict mode, bundler resolution |
| `aws/task-definition.json` | ECS Fargate task template with env var placeholders |

## Related pages

- [Backend](backend.md) — Django app responsibilities and base models
- [Frontend](frontend.md) — React architecture and module boundaries
- [Code Quality Rules](code-quality.md) — size / complexity limits and dependency directions
- [Deployment: Environments](../deployment/environments.md) — How config maps to each environment
