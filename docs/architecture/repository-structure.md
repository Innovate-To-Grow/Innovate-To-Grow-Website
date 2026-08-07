# Repository Structure

## Top-level layout

```
.
├── src/                    # Django backend (all Python code)
│   ├── apps/               # Django apps
│   │   ├── core/           # Framework, settings models, middleware, durable jobs
│   │   ├── authn/          # Authentication, Member, contacts, invitations
│   │   ├── cms/            # CMS pages, news, analytics, menus, footer
│   │   ├── event/          # Registration, ticketing, schedule, check-in
│   │   ├── projects/       # Past projects, semesters, sharing
│   │   ├── mail/           # Campaigns, recipient logs, login links
│   │   ├── system_intelligence/  # Admin AI assistant (agents, actions, exports)
│   │   ├── cli_admin/      # OAuth2 + PKCE CRUD API for the i2g-admin CLI
│   │   └── common/         # Opt-in shared building blocks (not wired in globally)
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
├── aws/                    # ECS task definition template
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

Not every app has all directories — `system_intelligence/` has no public REST surface, and
`common/` is a small flat-file app. A directory is used only where there is more than one
module to hold; single-module concerns stay as plain `.py` files (for example
`apps/core/middleware.py`, `apps/cms/cms_urls.py`).

### A note on `apps/core`

`core` holds the framework primitives every other app builds on — `ProjectControlModel`,
the model mixins, `BaseModelAdmin`, `access.py`, middleware, and the service-credential
singletons — but it has also accumulated three larger subsystems that are only *used* by
other apps rather than being framework-level concerns:

| Subsystem | Path | Importing apps |
|---|---|---|
| Bedrock LLM client | `core/services/bedrock/` | `mail`, `projects`, `system_intelligence` |
| ORM sandbox / AI tools | `core/services/db_tools/` | `cli_admin`, `system_intelligence` |
| Durable job queue | `core/services/background_jobs/` | `authn`, `cms`, `event`, `mail` |
| AWS credentials + SNS SMS | `core/services/aws/` | `authn`, `event`, `mail` |

`src/apps/core/services/__init__.py` carries the same table as a module docstring, so the map
is visible from an editor without opening the docs.

Splitting these into their own apps would be a clearer layering, but it requires new Django
app labels. That is deferred: `apps/core/access.py` and `Member.admin_apps` store app labels
**in the database** (a `JSONField` per admin user), so a new label needs a data migration to
backfill existing admins' grants or they silently lose access.

## Frontend source layout

```
pages/src/
├── app/                # Bootstrap: App component, Container, providers
├── router/             # Route definitions (lazy-loaded)
├── pages/              # Routed page components (HomePage, NewsPage, etc.)
├── components/         # UI components (Auth, CMS, Layout, MainMenu, Footer)
├── features/           # Domain API modules (analytics, cms, events, layout, news, projects)
├── shared/             # Cross-cutting: auth helpers, API client, hooks, utilities
├── services/           # API service barrel exports and crypto
├── styles/             # Design tokens and shared CSS
├── __tests__/          # Frontend test files
└── main.tsx            # Entry point: mounts three React roots
```

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
- [Deployment: Environments](../deployment/environments.md) — How config maps to each environment
