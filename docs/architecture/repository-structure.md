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
│   │   ├── helpdesk/       # Tickets from the i2g@ mailbox (shadow mode)
│   │   ├── system_intelligence/  # Admin AI assistant (agents, actions, exports)
│   │   └── cli_admin/      # OAuth2 + PKCE CRUD API for the i2g-admin CLI
│   ├── config/             # Django settings (base/, production/ overrides, environments/ entrypoints), routing/, deploy/ (ASGI/WSGI)
│   ├── assets/             # Pinned third-party static libs (vendor/), app-agnostic
│   ├── docker/             # Container pieces: entrypoint.sh and security/ (Debian package floors the image installs)
│   ├── requirements/       # base.txt (shared) ← production.txt (servers, PostgreSQL, Redis, S3) ← local.txt (+ dev/CI tooling)
│   ├── requirements.txt    # `-r requirements/local.txt`: the include every consumer uses (pip, Docker, pip-audit)
│   ├── manage.py           # Django management entry point
│   ├── Dockerfile          # Production container image (build context is src/)
│   ├── .env.example        # Template for src/.env (local environment variables, not in version control)
│   └── .dockerignore
├── pages/                  # React frontend (TypeScript + Vite)
│   ├── src/                # Application source (layout below)
│   ├── e2e/                # Playwright specs and helpers
│   ├── public/             # Static files copied into the build as-is (robots.txt, assets/)
│   ├── scripts/            # check-structure, quality-report, built-output checks, homepage timing
│   ├── index.html          # HTML shell with independently mounted React roots
│   ├── package.json        # Node dependencies and scripts
│   ├── vite.config.ts      # Dev server proxy and build config
│   ├── vitest.config.ts    # Test runner config
│   ├── playwright.config.ts
│   └── eslint.config.js, eslint.quality.js, tsconfig*.json
├── cli/                    # Standalone i2g-admin Python CLI (own pyproject.toml, uv.lock, tests)
├── archive/                # legacy/webpages.zip (old-site fixture for the legacy-view tests) and page/ (Flask archive service)
├── aws/                    # ecs/ (backend + archive task-definition templates), cicd/ (deploy-config keys, identity stack),
│                           #   ci-runners/ (Terraform for the self-hosted runners), legacy/ (CloudFormation + nginx of the old site)
├── scripts/                # ci/ (planner, validators, quality + dependency checks, and their tests), deploy/ (load_config,
│                           #   migrate_ecs, publish_image, validate_backend_task_definition), dev/ (e2e-local.sh), pre-commit/
├── docs/                   # Technical documentation (this directory): api/, architecture/, cms-admin/, deployment/, integrations/
├── .github/                # workflows/ (CI/CD), actions/ (composite setup actions), codeql/, dependabot.yml, actionlint.yaml
├── pyproject.toml          # Ruff, Bandit and coverage config for src/
├── .pre-commit-config.yaml # Local git hooks (fast checks on commit, Bandit + frontend checks on push)
├── .bandit-baseline.json   # Accepted Bandit findings; only new ones fail
├── .gitleaksignore         # Reviewed gitleaks fingerprints
├── CONTRIBUTING.md         # Contributor guidelines
└── README.md               # Project overview with doc links
```

Nothing else lives at the root. Every directory above has one owner-level purpose: application code under `src/`,
`pages/`, `cli/` and `archive/page/`; infrastructure templates under `aws/`; automation under `scripts/` and
`.github/`; prose under `docs/`.

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
stay as plain `.py` files (for example `apps/core/renderers.py`, `apps/cms/signals.py`,
`apps/mail/redirects.py`, `apps/system_intelligence/views.py`). The exceptions are the packages Django
or the migration history require: `management/commands/` is always a package, and
`apps/core/models/base/system_intelligence/` is a migration-compatibility shim that must stay byte-stable.

### A note on `apps/core`

`core` holds the framework primitives every other app builds on: `ProjectControlModel`,
the model mixins (`core/models/mixins.py`), reusable DRF utilities, `BaseModelAdmin`, `utils/access.py`, the
`middleware/` package, and the service-credential singletons. It also holds shared infrastructure
that names no business app:

| Subsystem | Path | Importing apps |
|---|---|---|
| Durable job queue | `core/services/background_jobs/` | `authn`, `cms`, `event`, `mail` (each registers its job kinds in `AppConfig.ready()`) |
| Read-only ORM sandbox | `core/services/db_tools/safe_orm/` | `cli_admin`, `system_intelligence` |
| AWS credentials, SMS sending and AWS limit reads | `core/services/aws/` | `authn`, `event`, `mail` |
| Email delivery (MIME, SES/SMTP/Graph/Gmail API) | `core/services/email/` | `authn`, `event`, `mail` |
| Delivery-rate limiter (Smart rate, budgets, stops) | `core/services/delivery_rates/` | `authn`, `event`, `mail` (job kinds declare a delivery family and lane in `register_job_kind`) |

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
that owns a name (for example `budget.cache_store._shared_redis_client`), not the package. The reverse
also holds: when a package is down to one module, flatten it back into a plain module with the same
import path, so callers and patch targets do not change.

### Settings packages (`src/config/settings/`)

Three sibling packages make up the settings, and only one of them is a settings module:

| Package | Role |
|---|---|
| `base/` | Everything shared: `framework/` (environment, Django, cache, the legacy-import shim) and `integrations/` (admin, API, editor, delivery rates, request limits, mail providers). `base/__init__.py` wildcard-imports them in order. |
| `production/` | Production overrides only (`django`, `security`, `storage`, `verification`, `cache`, `env`). Not a settings module on its own. |
| `environments/` | The entrypoints `DJANGO_SETTINGS_MODULE` names: `local` (SQLite, dev), `test` (PostgreSQL, E2E), `unit` (test + fast hashers, the CI test runner) and `production` (`base` + the `production/` overrides). |

## Frontend source layout

```
pages/src/
├── main.tsx            # Entry point: mounts the independent React roots
├── index.css           # Imports the contract, the shared styles and the app layout
├── app/                # Composition: providers/, router/ (routes + EMBED_APP_ROUTES), ErrorBoundary/,
│                       #   MaintenanceMode/, thirdPartyLoaders/
├── routes/             # Routed pages, lazy-loaded via deep imports; page-only hooks and sections
│                       #   live beside the page (e.g. EventRegistrationPage/registration/)
├── features/<domain>/  # assistant, auth, cms, events, layout, news, projects:
│                       #   api/, components/, optional hooks/, types.ts, public index.ts
├── components/         # Cross-feature UI, one folder per component (Icon/, NotFoundPage/, SafeHtml/,
│                       #   SheetsDataTable/, ResponsiveBrandImage/, ...)
├── hooks/              # Cross-feature hooks (useCopyLink, usePageTitle, usePageTracking, useReportFrameHeight)
├── lib/                # Framework-agnostic: api/ (client, error messages, embed hosts), format/, security/,
│                       #   css/, preview/, documentHead.ts, isolatedRoute.ts
├── types/              # Shared API types
├── styles/             # Every global stylesheet: tokens.css (fallback design tokens), shared.css, layers.css
│                       #   and contract/ (the CSS contract editors rely on)
└── __tests__/          # Vitest tests mirroring the source tree, plus core/ for project-level checks
                        #   (CSS contract and layers, index.html, lazy routes, barrels) and the Django admin
                        #   static JS evaluated in jsdom
```

Allowed imports between these layers are listed in
[Code Quality Rules](code-quality.md#frontend-layers) and checked by `npm run check:structure`.

## Configuration files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Ruff (line length 120, Python 3.11, double quotes, LF endings), Bandit and coverage settings for `src/` |
| `cli/pyproject.toml` | The CLI's own package metadata, dependencies and coverage settings |
| `src/.env` | Local env vars (SECRET_KEY, DB, AWS, Google Sheets) — not committed |
| `src/.env.example` | Template for `.env` with all expected variables |
| `src/requirements/*.txt` | Dependency inputs: `base.txt` → `production.txt` → `local.txt`; plain pins, no hashes |
| `pages/vite.config.ts` | Dev proxy to Django, manual code-splitting chunks |
| `pages/vitest.config.ts` | jsdom environment, 30s timeout |
| `pages/tsconfig.app.json` | ES2022 target, strict mode, bundler resolution |
| `aws/ecs/backend-task-definition.json` | ECS Fargate task template (web + background-worker containers) with env var placeholders |
| `aws/ecs/archive-task-definition.json` | ECS task template of the archive service |
| `aws/cicd/deploy-config-keys.json` | The allow-list of deploy-config keys `scripts/deploy/load_config.py` accepts |
| `scripts/ci/python_quality.toml`, `scripts/ci/python_dependencies.toml` | Size/complexity thresholds and app dependency rules |
| `.github/actionlint.yaml`, `.github/codeql/codeql-config.yml`, `.github/dependabot.yml` | Workflow lint, CodeQL and Dependabot settings |

## Related pages

- [Backend](backend.md) — Django app responsibilities and base models
- [Frontend](frontend.md) — React architecture and module boundaries
- [Code Quality Rules](code-quality.md) — size / complexity limits and dependency directions
- [Deployment: Environments](../deployment/environments.md) — How config maps to each environment
