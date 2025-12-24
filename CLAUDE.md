# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the UC Merced Innovate To Grow website, a full-stack application with a Django backend API and React frontend using Vite.

**Architecture:**
- **Backend:** Django REST Framework API (src/ directory)
- **Frontend:** React + TypeScript with Vite (pages/ directory)
- **Database:** SQLite for development (Django manages migrations)
- **Rich Text:** CKEditor for content management

## Development Setup

### Backend Setup (Django)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run migrations (from src/ directory)
cd src
python manage.py migrate

# Create superuser for admin access
python manage.py createsuperuser

# Run development server (port 8000)
python manage.py runserver
```

### Frontend Setup (React)

```bash
# Install Node dependencies
cd pages
npm install

# Run development server with proxy (port 5173)
npm run dev

# Build for production
npm run build

# Lint frontend code
npm run lint
```

### Running Both Servers

For full-stack development, run both servers simultaneously:
1. Django backend on http://localhost:8000
2. Vite frontend on http://localhost:5173 (proxies /api and /media to backend)

## Project Structure

### Backend (src/)

**Django Apps:**
- **core/** - Project configuration, settings (dev.py, prod.py), URL routing
- **authn/** - Authentication system with custom Member user model (extends AbstractUser)
- **pages/** - CMS for rich text pages with SEO fields and publishing controls
- **layout/** - Menu system and footer content management (JSON-based configuration)
- **notify/** - Verification system (email/SMS) and notification logging

**Key Models:**
- `Member` (authn/models/members/member.py) - Custom user model with UUID, contact info, and group management
- `Page` (pages/models/pages/page.py) - Rich text pages with CKEditor, supports nested slugs and external URLs
- `HomePage` (pages/models/pages/home_page.py) - Singleton model for homepage content
- `Menu` (layout/models/menu.py) - Hierarchical navigation menus with JSON items
- `FooterContent` (layout/models/footer_content.py) - JSON-configured footer (columns, CTAs, social links)
- `VerificationRequest` (notify/models/verification.py) - Email/SMS verification challenges

**Settings Structure:**
- base.py - Common settings for all environments
- dev.py - Development settings (DEBUG=True, uses SQLite)
- prod.py - Production settings (load from environment variables)
- Default: `DJANGO_SETTINGS_MODULE=core.settings.dev`

### Frontend (pages/)

**Structure:**
- **src/components/** - React components (Layout, MainMenu, Footer, PageContent)
- **src/pages/** - Route-level page components (Home.tsx)
- **src/router/** - React Router configuration
- **src/services/** - API client (axios) and TypeScript interfaces

**API Integration:**
- Vite proxy forwards `/api/*` and `/media/*` to Django backend
- Main endpoints: `/api/pages/{slug}/`, `/api/home/`, `/api/footer/`, `/api/menus/`
- TypeScript interfaces in services/api.ts match Django serializers

## Common Commands

### Django Management

```bash
# Create new migration after model changes
cd src
python manage.py makemigrations
python manage.py migrate

# Run Django tests
python manage.py test

# Collect static files for production
python manage.py collectstatic

# Access Django shell
python manage.py shell

# Run specific test
python manage.py test pages.tests.test_models
```

### Database

- **Database file:** src/db.sqlite3
- Migrations are in each app's migrations/ directory
- Reset database: delete db.sqlite3 and re-run migrations

### Frontend Development

```bash
cd pages

# Type checking
npm run build  # Includes tsc -b

# Preview production build
npm run preview
```

## API URL Structure

**Django URLs (core/urls.py):**
- `/admin/` - Django admin interface
- `/admin/preview-popup/` - Live editing preview
- `/api/pages/` - Page content endpoints (pages app)
- `/api/home/` - Homepage content
- `/api/footer/` - Footer configuration (layout app)
- `/api/menus/` - Menu structure (layout app)
- `/api/notify/` - Notification/verification endpoints
- `/api/authn/` - Authentication endpoints (currently empty)

**React Routes:**
- `/` - Homepage
- `/pages/:slug` - Dynamic pages (supports nested slugs like "about/team")

## Architecture Notes

### Content Management Flow
1. Admin creates/edits content in Django Admin (port 8000/admin/)
2. Content stored in SQLite with rich text via CKEditor
3. REST API exposes content as JSON
4. React frontend fetches and renders content
5. SEO metadata (meta_title, og_image, etc.) handled per-page

### Custom User Model
The project uses a custom `Member` model instead of Django's default User. This affects:
- AUTH_USER_MODEL = "authn.Member" in settings
- Migrations reference authn.Member
- Authentication flows use member_uuid for identification

### Rich Text Editors
- CKEditor for most content (with image upload support via MEDIA_URL)
- Uploads stored in src/media/uploads/
- Frontend renders HTML via dangerouslySetInnerHTML

### Layout System
Footer and menus use JSON fields for flexible configuration:
- FooterContent.content (JSONField) stores columns, CTAs, social links
- Menu.items (JSONField) stores hierarchical navigation structure
- Admin interfaces provide custom forms for editing JSON data

## Environment Variables

Create `src/.env` for local development (see src/.env.example):
- SECRET_KEY - Django secret key
- DEBUG - Debug mode flag
- ALLOWED_HOSTS - Comma-separated allowed hosts
- Database configuration (PostgreSQL for production)
- CKEditor settings

## Testing

Django tests are organized by app:
- pages/tests/ - Page model, view, and serializer tests
- authn/test/ - Authentication tests
- layout/admin/ - Admin interface customizations
- Run with `python manage.py test [app_name]`

## Migration Management

- Each app manages its own migrations in migrations/ directory
- Recent migration activity involves removing unused models and consolidating notification system
- Always run `makemigrations` before `migrate` when models change
- Check git status shows recent migration deletions (0001_initial.py files removed from authn/layout)
