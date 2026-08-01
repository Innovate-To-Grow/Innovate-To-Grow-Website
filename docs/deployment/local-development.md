# Local Development

Setting up and running the project for local development.

## Prerequisites

- Python 3.11+
- Node.js 22.22+ with npm 10+
- Git
- Docker Desktop or another Docker daemon (only for live Playwright tests)

## Backend setup

```bash
# Run from the repository root. Create and activate the shared virtual environment.
python3.11 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install the reproducible local/test dependency set
python -m pip install --require-hashes -r src/requirements/local.lock.txt

# Configure environment
cp src/.env.example src/.env
# Edit .env for any integrations you want to exercise locally.
# config.settings.local supplies a development-only SECRET_KEY.

# Run migrations
cd src
python manage.py migrate

# Create admin user (prompts for email, not username)
python manage.py createsuperuser

# Seed skeleton service configs (optional)
python manage.py seed_service_configs

# Enter SES, SMS, or Google credentials via Django admin → Site Settings.
# Verify configs before deploying to prod:
# python manage.py verify_service_configs --strict

# Start the server
python manage.py runserver
```

Django runs at `http://localhost:8000`. Admin is at `http://localhost:8000/admin/`.

### Settings

Local development uses `config.settings.local` by default. Key behaviors:
- `DEBUG = True`
- SQLite database (`src/db.sqlite3`)
- Emails printed to console
- In-memory cache
- `ALLOWED_HOSTS`: `localhost`, `127.0.0.1`, `0.0.0.0`

Most Django commands pick up dev settings automatically. For `test`, you must specify explicitly:

```bash
python manage.py test --settings=config.settings.local
```

### Database reset

For a clean slate (destroys all data):

```bash
python manage.py resetdb --force
```

This drops the database, regenerates migrations, migrates, and seeds a default admin user (`admin@localhost` / password: `changeme`). Override those disposable local credentials with `DEV_ADMIN_EMAIL` and `DEV_ADMIN_PASSWORD`. Dev-only — the command has safety guards against production databases.

### Migration graph and ordering

Use Django's dependency graph instead of applying the new invariant migrations individually:

| App | Required chain |
|-----|----------------|
| `authn` | `0015_emailauthchallenge_channel_sms` → `0016_backfill_primary_email` → `0017_auth_security_invariants` |
| `core` | `0026_remove_emailserviceconfig_smtp_fields` → `0027_backgroundjob` → `0028_active_config_invariants` → `0029_deliveryratelimit` |
| `event` | `0008_event_date_range_and_registration_status` → `0009_registration_sheet_sync_audit` → `0010_active_schedule_invariant` |
| `projects` | `0007_project_resource_admin_names` → `0008_pastprojectshare_version` → `0009_active_sheet_config_invariant` |
| `system_intelligence` | `0004_systemintelligenceconfig_public_assistant_log_enabled_and_more` → `0005_active_config_invariant` → `0006_public_assistant_input_limits` |

The active-configuration migrations first choose one deterministic winner from any duplicate active rows, deactivate the others, and only then add partial unique constraints. Do not fake these migrations unless the schema and normalized data have been independently verified.

These are app-local chains, not a hand-authored global sequence. Run the full graph and let Django topologically order independent apps.

Preview and apply the local SQLite plan:

```bash
cd src
python manage.py showmigrations authn core event projects system_intelligence
python manage.py migrate --plan
python manage.py migrate
```

`migrate_locked` deliberately refuses SQLite. On a PostgreSQL environment, operators use the same Django migration interface under a session advisory lock:

```bash
python manage.py migrate_locked --noinput --lock-timeout-seconds 600
```

Only one caller can hold that repository-specific lock. A timed-out caller exits without running migrations.

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
python manage.py run_background_worker --once                           # Process one durable-job batch
python manage.py migrate                                                # Apply migrations
python manage.py migrate --plan                                         # Preview unapplied operations
python manage.py makemigrations --check --dry-run                        # Assert model/migration parity
python manage.py test --settings=config.settings.local                   # Run all tests
python manage.py test apps.authn.tests.api.test_session.SessionViewTests --settings=config.settings.local  # Single test class
ruff check .                                                            # Lint
ruff check . --fix                                                      # Auto-fix lint
ruff format .                                                           # Format
python manage.py sync_news --settings=config.settings.local              # Sync RSS feeds
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

## Playwright browser tests

Playwright has two intentionally separate suites:

- `npm run e2e` (the same as `npm run e2e:local`) runs fixture-backed browser
  tests. It builds and starts a local Vite preview automatically. The shared
  fixture and each spec mock the API requests they use; Django, PostgreSQL,
  Redis, AWS, and Google credentials are not required.
- `npm run e2e:live` runs only the `live-chromium` project. It exercises the
  real Django readiness endpoint and the seeded admin flows against an
  ephemeral PostgreSQL database.

Install browser binaries once, then run the dependency-free suite:

```bash
cd pages
npm run e2e:install
npm run e2e
```

The live suite is also one command after the normal backend and frontend
dependency setup above:

```bash
# Docker must be running. These ports must be free:
#   4173 (Vite), 8000 (Django), 55432 (ephemeral PostgreSQL)
cd pages
npm run e2e:live
```

The live configuration invokes `scripts/e2e/run-live-backend.sh`, which:

1. Starts a disposable PostgreSQL 16 container bound to `127.0.0.1:55432`.
2. Uses `config.settings.test`, applies every migration, and runs
   `seed_admin_e2e --yes`.
3. Starts Django with admin static files and builds/starts the Vite preview.
4. Stops and removes the PostgreSQL container when Playwright exits.

The script expects the documented backend virtual environment at
`.venv/bin/python` in the repository root. Override it with `I2G_E2E_PYTHON`, the host database
port with `I2G_E2E_DB_PORT`, or the PostgreSQL image with
`I2G_E2E_POSTGRES_IMAGE`. Admin seed credentials can be overridden with the
`ADMIN_E2E_*` variables used by `seed_admin_e2e`; the matching variables are
read by `pages/e2e/admin.spec.ts`.

CI uses the same project boundary. Ordinary browser/device projects run only
mocked specs. The `live-chromium` matrix leg starts the workflow's PostgreSQL
service, applies migrations, seeds deterministic admin data, starts Django and
the exact prebuilt Vite artifact, then runs the live/admin specs.

## Development workflow

1. Start Django from `src/`
2. Start Vite from `pages/`
3. Make changes — Vite provides HMR, Django auto-reloads on Python changes
4. Before finishing, run the validation suite:

```bash
# Backend
cd src && ruff check . && ruff format --check . && python manage.py test --settings=config.settings.local

# Frontend
cd pages && npm run lint && npx tsc --noEmit && npm test && npm run build
```

## Gotchas

- **Settings flag**: Always pass `--settings=config.settings.local` to `test` and `sync_news` commands. `runserver` and `migrate` pick it up from defaults.
- **Superuser creation**: Uses email, not username. For non-interactive mode: `python manage.py createsuperuser --email admin@example.com`
- **Three React roots**: If you change auth behavior, test that the menu and footer roots also update correctly.
- **Migration edits**: Never edit a migration that has been merged to `main`. Create a new migration instead.
- **SMS configuration boundary**: Requesting an SMS code needs one explicitly active, configured `AWSCredentialConfig`. Verifying an already-sent code reads the durable challenge row and does not call AWS.
- **SMS challenge IDs**: New consumers must retain each request response's `challenge_id` and send it to the matching verify endpoint. Phone-number/code-only verification is a one-release compatibility path.

## Backend authentication smoke checks

After applying the migration graph, run:

```bash
cd src
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test \
  apps.authn.tests.api.test_session \
  apps.authn.tests.api.phone_code.test_phone_code_login \
  apps.authn.tests.api.test_impersonate_login \
  apps.authn.tests.services.test_rsa_service \
  --settings=config.settings.local
```

For a local integration check, start Django and confirm:

```bash
curl -fsS http://localhost:8000/authn/public-key/
curl -i http://localhost:8000/authn/session/
```

The public-key request should return `200` with `key_id` and `public_key`. The unauthenticated session request should return `401`; a bearer access token is required for its authoritative profile response.

## Related pages

- [Environments](environments.md) — Configuration differences across environments
- [CI/CD](ci-cd.md) — What runs in the CI pipeline
- [Architecture: Repository Structure](../architecture/repository-structure.md) — Directory layout
