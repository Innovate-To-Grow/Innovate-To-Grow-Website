# Local Development

Setting up and running the project for local development.

## Prerequisites

- Python 3.11+
- Node.js 18+ LTS with npm 10+
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

# Seed service configs from .env (optional)
python manage.py seed_service_configs

# Start the server
python manage.py runserver
```

Django runs at `http://localhost:8000`. Admin is at `http://localhost:8000/admin/`.

### Settings

Local development uses `core.settings.dev` by default. Key behaviors:
- `DEBUG = True`
- SQLite database (`src/db.sqlite3`)
- Emails printed to console
- In-memory cache
- `ALLOWED_HOSTS`: `localhost`, `127.0.0.1`, `0.0.0.0`

Most Django commands pick up dev settings automatically. For `test`, you must specify explicitly:

```bash
python manage.py test --settings=core.settings.dev
```

### Database reset

For a clean slate (destroys all data):

```bash
python manage.py resetdb --force
```

This drops the database, regenerates migrations, migrates, and seeds a default admin user (`hongzhe` / `xiehongzhe04@gmail.com` / password: `1`). Dev-only — has safety guards against production databases.

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
python manage.py test --settings=core.settings.dev                      # Run all tests
python manage.py test authn.tests.test_api.LoginTest --settings=core.settings.dev  # Single test class
ruff check .                                                            # Lint
ruff check . --fix                                                      # Auto-fix lint
ruff format .                                                           # Format
python manage.py sync_news --settings=core.settings.dev                 # Sync RSS feeds
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

## Development workflow

1. Start Django from `src/`
2. Start Vite from `pages/`
3. Make changes — Vite provides HMR, Django auto-reloads on Python changes
4. Before finishing, run the validation suite:

```bash
# Backend
cd src && ruff check . && ruff format --check . && python manage.py test --settings=core.settings.dev

# Frontend
cd pages && npm run lint && npx tsc --noEmit && npm test && npm run build
```

## Gotchas

- **Settings flag**: Always pass `--settings=core.settings.dev` to `test` and `sync_news` commands. `runserver` and `migrate` pick it up from defaults.
- **Superuser creation**: Uses email, not username. For non-interactive mode: `python manage.py createsuperuser --email admin@example.com`
- **Three React roots**: If you change auth behavior, test that the menu and footer roots also update correctly.
- **Migration edits**: Never edit a migration that has been merged to `main`. Create a new migration instead.

## Related pages

- [Environments](environments.md) — Configuration differences across environments
- [CI/CD](ci-cd.md) — What runs in the CI pipeline
- [Architecture: Repository Structure](../architecture/repository-structure.md) — Directory layout
