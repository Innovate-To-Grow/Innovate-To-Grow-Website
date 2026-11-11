# Local Development

Setting up and running the project for local development.

## Prerequisites

- Python 3.11+
- Node.js 22.22.2 with npm 10+ (or another release allowed by `pages/package.json`)
- Git

## Backend setup

```bash
cd src

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values (at minimum, set DJANGO_SECRET_KEY)

# Run migrations
python manage.py migrate

# Create admin user (prompts for email, not username)
python manage.py createsuperuser

# Seed skeleton service configs (optional)
python manage.py seed_service_configs

# Enter SES, SMTP, Microsoft Graph, SNS, or Google credentials via Django admin
# (Site Settings; the email provider and SMTP are under Mail → Notification Delivery, and the
# Microsoft Graph configuration and certificate under /admin/core/microsoftgraphproviderconfig/).
# Verify configs before deploying to prod:
# python manage.py verify_service_configs --strict

# Start the server
python manage.py runserver
```

Django runs at `http://localhost:8000`. Admin is at `http://localhost:8000/admin/`.

### Settings

Local development uses `config.settings.environments.local` by default. Key behaviors:
- `DEBUG = True`
- SQLite database (`src/db.sqlite3`)
- Emails printed to console
- In-memory cache
- `DJANGO_ALLOWED_HOSTS`: `localhost`, `127.0.0.1`, `0.0.0.0`
- Private keys installed in the admin (the Microsoft Graph certificate key) go to the local file store,
  `src/data/credential-store/` (`CREDENTIAL_STORE_BACKEND = "local_file"`): a 0700 directory of 0600
  files, gitignored and excluded from the Docker image. Use throwaway keys only; never install the
  production key in a local site. Under `manage.py test` the store is process memory instead. The Graph
  go-live gate (`GRAPH_REQUIRE_ACCESS_EVIDENCE`) is off locally. See
  [Environments](environments.md#microsoft-graph-email).

Most Django commands pick up dev settings automatically. For `test`, you must specify explicitly:

```bash
python manage.py test --settings=config.settings.environments.local
```

### Database reset

For a clean slate (destroys all data):

```bash
python manage.py resetdb --force --confirm RESET_DB
```

This drops the database, regenerates migrations, migrates, creates a default superuser and seeds the service configs and the archive CMS pages, menus and footer. Sign in as the superuser with `admin@localhost` / password `changeme` (set `DEV_ADMIN_EMAIL` and `DEV_ADMIN_PASSWORD` in `src/.env` to change them). Dev-only — it refuses to run unless `DEBUG` is on (or `--allow-production` is given).

## Frontend setup

```bash
cd pages

# Install dependencies
npm ci

# Start dev server
npm run dev
```

Vite runs at `http://localhost:5173` and proxies these paths to Django:
- `/api/*`
- `/media/*`
- `/static/*`

The backend URL is configurable via `VITE_BACKEND_URL` env var (defaults to `http://127.0.0.1:8000`).

## Common commands

### Backend

```bash
cd src
python manage.py runserver                                              # Start dev server
python manage.py migrate                                                # Apply migrations
python manage.py makemigrations                                         # Generate migrations
python manage.py test --settings=config.settings.environments.local                      # Run all tests
python manage.py test apps.authn.tests.test_api.LoginTest --settings=config.settings.environments.local  # Single test class
ruff check .                                                            # Lint
ruff check . --fix                                                      # Auto-fix lint
ruff format .                                                           # Format
python manage.py sync_news --settings=config.settings.environments.local                 # Sync RSS feeds
```

### Frontend

```bash
cd pages
npm run dev          # Vite dev server with HMR
npm run lint         # ESLint
npx tsc --noEmit     # TypeScript type check
npm test             # Vitest
npm run build        # Production build (tsc -b + vite build)
```

### End-to-end tests (Playwright)

Most specs mock the API, but the live specs (`pages/e2e/smoke/live.spec.ts` and the Django-admin flow in
`pages/e2e/admin/`) talk to a real backend configured the way CI configures it. `scripts/dev/e2e-local.sh` sets
that up without Docker or PostgreSQL: it migrates and seeds a throwaway SQLite database under `src/` with
`config.settings.environments.test` (`seed_admin_e2e`), starts `runserver --insecure` on port 8000, and runs
`npx playwright test` with any arguments you pass. Ports 8000 and 4173 must be free.

```bash
cd pages && npm run e2e:install                            # once: install the browsers
scripts/dev/e2e-local.sh                                   # the full 10-project matrix
scripts/dev/e2e-local.sh --fresh e2e/smoke/live.spec.ts    # one spec against a fresh database
```

## Development workflow

1. Start Django from `src/`
2. Start Vite from `pages/`
3. Make changes — Vite provides HMR, Django auto-reloads on Python changes
4. Before finishing, run the validation suite:

```bash
# Backend
cd src && ruff check . && ruff format --check . && python manage.py test --settings=config.settings.environments.local

# Frontend
cd pages && npm run lint && npx tsc --noEmit && npm test && npm run build
```

## Gotchas

- **Settings flag**: Always pass `--settings=config.settings.environments.local` to `test` and `sync_news` commands. `runserver` and `migrate` pick it up from defaults.
- **Superuser creation**: Uses email, not username. For non-interactive mode: `python manage.py createsuperuser --email admin@example.com`
- **Three React roots**: If you change auth behavior, test that the menu and footer roots also update correctly.
- **Migration edits**: Never edit a migration that has been merged to `main`. Create a new migration instead.

## Related pages

- [Environments](environments.md) — Configuration differences across environments
- [CI/CD](ci-cd.md) — What runs in the CI pipeline
- [Architecture: Repository Structure](../architecture/repository-structure.md) — Directory layout
