# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UC Merced Innovate to Grow (ITG) website with a Django REST Framework backend (`src/`) and React + TypeScript + Vite frontend (`pages/`).

- **Backend**: Django 4.2, DRF 3.15, Python 3.11+, SQLite (dev) / PostgreSQL (prod)
- **Frontend**: React 19, TypeScript 5.9, Vite 7, Axios
- **Auth**: Custom `authn.Member` model (UUIDs, custom fields) with JWT tokens

## Common Commands

### Backend (Django)
```bash
cd src

# Development server
python manage.py runserver                    # Start dev server on :8000

# Database
python manage.py migrate                      # Apply migrations
python manage.py makemigrations               # Create new migrations
python manage.py createsuperuser              # Create admin user

# Testing
python manage.py test                         # Run all tests
python manage.py test pages.tests.test_views  # Run specific test module

# Linting
ruff check .                                  # Check for issues
ruff check . --fix                            # Auto-fix issues
ruff format .                                 # Format code

# Custom management commands
python manage.py resetdb --force --confirm RESET_DB   # Reset database (dev only)
python manage.py export_pages about -o about.zip      # Export page with media
python manage.py import_pages about.zip               # Import page with media
```

### Frontend (React + Vite)
```bash
cd pages

# Development
npm install                                   # Install dependencies
npm run dev                                   # Start Vite dev server on :5173

# Production build
npm run build                                 # TypeScript check + build
npm run preview                               # Preview production build

# Linting
npm run lint                                  # Run ESLint
npx tsc --noEmit                             # Type check only
```

### Pre-commit Hooks
```bash
# Setup (from project root)
pip install pre-commit
pre-commit install

# Runs automatically on commit, or manually:
pre-commit run --all-files
```

## Architecture

### Django Apps

The backend is organized into specialized Django apps:

- **`core/`**: Project configuration, settings (base/dev/prod), health check, versioning system
- **`pages/`**: CMS for managing Page and HomePage models with components (HTML/CSS/JS blocks)
- **`authn/`**: Custom authentication with UUID-based Member model and JWT
- **`events/`**: Event management with registration, presentation schedules, and Google Sheets sync API
- **`notify/`**: Email/SMS verification and notification system
- **`mobileid/`**: Mobile ID validation integration
- **`layout/`**: Site-wide layout elements (menus, footers) - **merged into pages app**

### Settings Structure

Django settings are split across three files in `src/core/settings/`:

- **`base.py`**: Shared configuration for all environments
- **`dev.py`**: Local development overrides (DEBUG=True, console email)
- **`prod.py`**: Production settings (security, PostgreSQL, Redis, S3/R2 storage)

Set `DJANGO_SETTINGS_MODULE` environment variable or use `--settings` flag.

### Frontend Architecture

- **`pages/src/services/api.ts`**: Centralized API calls and TypeScript interfaces. Keep backend serializers in sync with these types.
- **`pages/src/components/`**: Reusable React components organized by feature:
  - `Layout/`: Site layout components (MainMenu, Footer)
  - `PageContent/`: Page rendering components
  - `Event/`: Event display components
  - `Auth/`: Authentication UI
  - `MaintenanceMode/`: Maintenance mode handling
- **`pages/src/router/`**: React Router configuration
- **Vite proxy**: `/api`, `/media`, `/admin` proxied to backend (localhost:8000)

### Page Component System

Pages and homepages support dynamic components via `PageComponent` model:

- **Component types**: `html`, `form`, `google_sheet`, `sheet`
- **Fields**: `html_content`, `css_file`, `css_code`, `js_code`, `config` (JSON)
- **Ordering**: Components render in `order` field sequence
- **Admin preview**: Live preview available in Django admin at `/admin/preview-popup/`

### API Contracts

When modifying API responses:

1. Update Django serializer (`*Serializer` class)
2. Update TypeScript interface in `pages/src/services/api.ts`
3. Update API function if needed
4. Run `npm run build` to verify TypeScript compilation

### Events Sheet Sync

Special API for Google Apps Script integration:

- **Endpoint**: `/api/events/sync/export/`
- **Auth**: `X-API-Key` header with `EVENTS_API_KEY`
- **Modes**: `full` (complete snapshot) or `delta` (changed since watermark)
- **Documentation**: `docs/events-sheet-sync.md`

## Development Workflow

### Full-Stack Local Development

1. Start backend: `cd src && python manage.py runserver` (port 8000)
2. Start frontend: `cd pages && npm run dev` (port 5173)
3. Visit http://localhost:5173 (Vite auto-proxies `/api` to Django)
4. Admin interface: http://localhost:5173/admin

### Working with Migrations

- **Never edit** existing migrations on `main` branch
- Generate migrations after model changes: `python manage.py makemigrations`
- Always commit generated migration files
- Fixtures in `src/layout/fixtures/` - load with `python manage.py loaddata layout/fixtures/<file>.json`

### Git Workflow

- Branch naming: `feature/<desc>`, `fix/<bug-id>`, `docs/<topic>`
- Rebase before PR: `git pull --rebase upstream main`
- Reference issues: Use `Fixes #123` in commits and PR descriptions

## Code Style

### Python (Backend)

- **Linter**: Ruff (combines pycodestyle, pyflakes, isort, flake8-bugbear, pyupgrade, flake8-django)
- **Line length**: 120 characters
- **Import order**: Standard library → Django → Third-party → First-party (see `pyproject.toml`)
- **Type hints**: Use where possible
- **Business logic**: Put in `services/` modules when not in models/serializers

### TypeScript (Frontend)

- **Functional components** with hooks only (no class components)
- **API calls**: Centralized in `pages/src/services/api.ts`
- **CSS**: Co-locate CSS modules with components (`Component.css`)
- **Layout primitives**: Use shared components (`Layout/`, `MainMenu`, `Footer`) for consistency

### Ruff Configuration

Key ignored rules (see `pyproject.toml`):

- `E501`: Line too long (handled by formatter)
- `B008`: Function calls in argument defaults (needed for Django)
- `DJ001`: null=True on string fields (existing pattern)
- `F403/F405`: Star imports (used in Django settings)

## Testing

- **Backend tests**: `cd src && python manage.py test`
- **CI/CD**: GitHub Actions runs Ruff + ESLint + TypeScript checks on every push/PR
- Add tests when:
  - Creating/changing models, serializers, services
  - Modifying API endpoints
  - Introducing new React components/hooks
  - Fixing bugs (include regression test)

## Environment Variables

Create `src/.env` from `src/.env.example`:

```bash
cp src/.env.example src/.env
# Edit src/.env with your values
```

Key variables:

- `DJANGO_SETTINGS_MODULE`: Settings module (e.g., `core.settings.dev`)
- `SECRET_KEY`: Django secret key
- `EVENTS_API_KEY`: API key for events sheet sync
- Backend URL for Vite: Set `VITE_BACKEND_URL` if not using default localhost:8000

## Documentation

- **Setup guide**: `CONTRIBUTING.md` (comprehensive setup and workflow)
- **Events API**: `docs/events-sheet-sync.md`
- **Legacy parity**: `docs/event-legacy-parity-plan.md`
