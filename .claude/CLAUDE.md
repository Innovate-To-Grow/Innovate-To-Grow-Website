# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UC Merced Innovate to Grow (ITG) website with a Django REST Framework backend (`src/`) and React + TypeScript + Vite frontend (`pages/`).

- **Backend**: Django 5.2, DRF 3.16, Python 3.11+, SQLite (dev) / PostgreSQL (prod)
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
python manage.py test --settings=core.settings.dev                         # Run all tests
python manage.py test pages.tests.test_views --settings=core.settings.dev  # Run specific test module

# Linting
ruff check .                                  # Check for issues
ruff check . --fix                            # Auto-fix issues
ruff format .                                 # Format code

# Custom management commands
python manage.py resetdb --force --confirm RESET_DB   # Reset database (dev only)
python manage.py seed_initial_data                     # Seed menu and footer data
python manage.py sync_news                             # Sync news from feed sources
python manage.py test_gmail_connection                 # Test Gmail API connection
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

- **`core/`**: Project configuration, settings (base/dev/prod), health check, versioning system, middleware
- **`pages/`**: Layout (Menu, FooterContent), Google Sheets data proxy (GoogleSheetSource), SiteSettings, and block-based CMS (CMSPage, CMSBlock). CMS pages have a route, status (draft/published/archived), and ordered content blocks. Block types: hero, rich_text, faq_list, link_list, cta_group, image_text, notice, contact_info, google_sheet, section_group, table, numbered_list, proposal_cards, navigation_grid, schedule_grid. CMS API at `/cms/pages/<route>/` and preview at `/cms/preview/<token>/`. Sheets data at `/sheets/<slug>/`
- **`cms/`**: Migration-only stub (models moved to `pages`). Kept in `INSTALLED_APPS` for migration history
- **`authn/`**: Auth with Member model, JWT, email verification, contact emails/phones, password reset
- **`event/`**: Event management (Event, Ticket, Question models)
- **`news/`**: News articles (NewsArticle, NewsFeedSource, NewsSyncLog) and feed syncing
- **`projects/`**: Semester and project management (Semester, Project models)
- **`mail/`**: Email sending via Gmail API and AWS SES (GoogleAccount, SESAccount, EmailLog, SESEmailLog)

### Settings Structure

Django settings are split across three files in `src/core/settings/`:

- **`base.py`**: Shared configuration for all environments
- **`dev.py`**: Local development overrides (DEBUG=True, console email)
- **`prod.py`**: Production settings (security, PostgreSQL, Redis, S3/R2 storage)

Set `DJANGO_SETTINGS_MODULE` environment variable or use `--settings` flag.

### Frontend Architecture

- **`pages/src/services/api/`**: API calls split into modules (`client.ts`, `health.ts`, `layout.ts`, `news.ts`, `projects.ts`, `sheets.ts`, `cms.ts`). TypeScript interfaces in `types.ts` and alongside API functions. `auth.ts` and `crypto.ts` are at `pages/src/services/`.
- **`pages/src/components/`**: React components organized by feature (`Layout/`, `Auth/`, `CMS/`, `MaintenanceMode/`)
- **`pages/src/components/CMS/`**: CMS rendering system. `CMSPageComponent` fetches page data by route and renders blocks via `BlockRenderer`. Per-page CSS in `page-styles/`. The `useCMSPage` hook handles data fetching.
- **`pages/src/pages/`**: Data-driven pages with dedicated React components (each has `index.ts`, `PageName.tsx`, `PageName.css`): NewsPage, NewsDetailPage, ProjectsPage, PastProjectsPage, ProjectDetailPage, EventPage, SchedulePage, EventArchivePage, ProjectsTeamsPage, AcknowledgementPage, HomePage, NotFoundPage
- **`pages/src/router/`**: React Router configuration. `HomepageResolver` dynamically resolves the homepage based on `SiteSettings.homepage_route` from the layout API.
- **CMS vs dedicated pages**: Most content routes (about, faqs, contact-us, privacy, students, judges, sponsorship, etc.) use `CMSPageComponent` which renders CMS-managed content from the backend. Only data-driven routes (news, projects, events) have dedicated React components.
- **Routes**: See `pages/src/router/index.tsx` for full list. Key data-driven routes: `/news`, `/news/:id`, `/current-projects`, `/past-projects`, `/projects/:id`, `/event`, `/schedule`, `/events/:eventSlug`, `/projects-teams`, `/acknowledgement`. CMS routes: `/about`, `/projects`, `/faqs`, `/contact-us`, `/privacy`, `/ferpa`, `/judges`, `/attendees`, `/judging`, `/sponsorship`, `/students`, and more. Auth routes: `/login`, `/register`, `/forgot-password`, `/verify-email`, `/complete-profile`, `/account`. Many legacy URLs redirect to canonical paths.
- **Vite proxy**: `/api`, `/media`, `/admin` proxied to backend (localhost:8000)
- **Three React roots**: `#root` (main app with BrowserRouter), `#menu-root` (MainMenu only, no router), `#footer-root` (Footer only). Auth state syncs across roots via `i2g-auth-state-change` window event.

### ProjectControlModel (Base Model)

All main models inherit from `core.models.ProjectControlModel`, which provides:

- **UUID primary keys** (not auto-incrementing integers) — `id` is the UUID field
- **Soft delete**: `delete()` marks as deleted; `hard_delete()` for permanent removal; `restore()` to undelete
- **Version control**: `save_version()`, `get_versions()`, `rollback()`, `get_version_diff()`
- **Two managers**: `objects` (excludes soft-deleted) and `all_objects` (includes all)
- **Timestamps**: `created_at`, `updated_at` (auto-managed)

When querying, use `Model.objects` for normal queries and `Model.all_objects` when you need to include soft-deleted records.

### Authentication & Security

- **Member model**: `Member.id` is the UUID primary key. `member_uuid` is a `@property` alias for `id` — it is NOT a DB column.
- **JWT config**: `USER_ID_FIELD = "id"` (not `"member_uuid"`), `USER_ID_CLAIM = "member_uuid"`. Token blacklisting is enabled via `rest_framework_simplejwt.token_blacklist`.
- **Password encryption**: Passwords are RSA-encrypted client-side before transmission. `PublicKeyView` serves the key; `authn/services.py` handles decryption.
- **Email verification**: Registration requires email code verification (`RegisterVerifyCodeView`, `RegisterResendCodeView`). Login supports email code verification (`LoginCodeRequestView`, `LoginCodeVerifyView`).
- **Password reset**: Email code flow — request (`PasswordResetRequestView`) → verify code (`PasswordResetVerifyView`) → confirm new password (`PasswordResetConfirmView`). Change password also supports email code verification.
- **Contact emails**: CRUD at `/authn/contact-emails/` with verification (`ContactEmailListCreateView`, `ContactEmailDetailView`, `ContactEmailRequestVerificationView`, `ContactEmailVerifyCodeView`).
- **DEFAULT_PERMISSION_CLASSES is `IsAuthenticated`**: All DRF views require auth by default. Public views (login, register, pages) must explicitly set `permission_classes = [AllowAny]`.
- **Throttles**: `LoginRateThrottle` (10/min) in `src/authn/throttles.py`. Do NOT set `DEFAULT_THROTTLE_CLASSES` globally — it breaks tests at 127.0.0.1.

### Admin Interface

The admin uses **django-unfold** for theming and **CKEditor 5** for rich text editing. Configuration is in `src/core/settings/base.py` under `UNFOLD`. Custom admin templates live in `src/core/templates/unfold/helpers/`. CMS admin is at `/admin/pages/cmspage/`.

### Caching

- **Dev**: In-memory cache (`LocMemCache`)
- **Prod**: Redis via `django-redis`
- **Cache invalidation**: Signal handlers in `src/pages/signals.py` auto-clear cache when Menu, FooterContent, GoogleSheetSource, CMSPage, or CMSBlock are saved/deleted
- **Cache keys**: `"layout:data"`, `"sheets:<slug>:data"`, `"cms:page:<route>"`, `"cms:preview:<token>"`
- **Important**: When adding cache to views, ensure tests call `cache.clear()` in `setUp()` to prevent cross-test pollution.

### API Contracts

When modifying API responses:

1. Update Django serializer (`*Serializer` class)
2. Update TypeScript interface in the corresponding `pages/src/services/api/*.ts` module
3. Update API function if needed
4. Run `npm run build` to verify TypeScript compilation

### Health Check

- **Endpoint**: `/health-check/` — returns JSON with status and database connectivity
- Returns HTTP 503 if the database is unreachable

## Adding a New Frontend Page

**For CMS-managed pages** (static content like about, FAQ, etc.):

1. **Add route** in `pages/src/router/index.tsx` — use `CMSPageComponent` as the element
2. **Create CMS page** in Django admin — set the route to match, add content blocks, publish
3. **Optionally add page-specific CSS** in `pages/src/components/CMS/page-styles/` — the `page_css_class` field on CMSPage maps to the wrapper div class

**For data-driven pages** (pages with their own API calls, e.g., news, projects):

1. **Create page folder** `pages/src/pages/<PageName>/` with `PageName.tsx`, `PageName.css`, `index.ts`
2. **Register route** in `pages/src/router/index.tsx` — add import and route entry
3. **Register in admin menu editor** — add to `APP_ROUTES` list in `src/pages/app_routes.py` (only for non-CMS pages; CMS pages are loaded dynamically from the database in the menu editor)

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
- Fixtures in `src/pages/fixtures/` (e.g., `footer_content.json`) — load with `python manage.py loaddata pages/fixtures/<file>.json`

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
- **API calls**: Centralized in `pages/src/services/api/` (split by domain)
- **CSS**: Co-locate CSS modules with components (`Component.css`)
- **Layout primitives**: Use shared components (`Layout/`, `MainMenu`, `Footer`) for consistency

### Ruff Configuration

Key ignored rules (see `pyproject.toml`):

- `E501`: Line too long (handled by formatter)
- `B008`: Function calls in argument defaults (needed for Django)
- `B904`: raise without `from` in except (existing pattern)
- `DJ001`: null=True on string fields (existing pattern)
- `DJ007`: `__all__` not set in `ModelForm` (existing pattern)
- `DJ012`: Order of model inner classes/methods (existing pattern)
- `F403/F405`: Star imports (used in Django settings)

**Note**: `cms` is a migration-only stub — no linting needed. `known-first-party` lists `["core", "authn", "pages", "event", "news", "projects", "mail"]`.

## Testing

- **Backend tests**: `cd src && python manage.py test --settings=core.settings.dev`
- **CI/CD**: GitHub Actions (`lint.yml` + `ci.yml`) runs Ruff check/format, ESLint, TypeScript checks, Django migrations, and `python manage.py test` on pushes to main and all PRs
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
- API base URL for Vite: Set `VITE_API_BASE_URL` if not using default `/api` proxy

## Documentation

- **Setup guide**: `CONTRIBUTING.md` (comprehensive setup and workflow)
