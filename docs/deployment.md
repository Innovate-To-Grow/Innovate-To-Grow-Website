# Deployment Guide

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 20+ (LTS) and npm
- SQLite 3.35+ (bundled with Python)
- Git

### Backend Setup

```bash
cd src
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # then edit .env with your values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver  # starts on :8000
```

The dev settings (`core.settings.dev`) use SQLite and in-memory cache by default. No external services are required.

### Frontend Setup

```bash
cd pages
npm install
npm run dev    # starts Vite dev server on :5173
```

Vite proxies `/api/*`, `/media/*`, `/admin/*`, and `/static/*` to `http://localhost:8000`.

### Full-Stack Development

1. Start backend: `cd src && python manage.py runserver`
2. Start frontend: `cd pages && npm run dev`
3. Visit `http://localhost:5173` (Vite handles proxying to Django)
4. Admin: `http://localhost:5173/admin`

---

## Environment Variables

### Required in Production

| Variable | Purpose | Example |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | Django cryptographic signing | Random 50+ char string |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `api.example.com,example.com` |
| `DB_NAME` | PostgreSQL database name | `innovate_to_grow` |
| `DB_USER` | PostgreSQL user | `itg_user` |
| `DB_PASSWORD` | PostgreSQL password | — |
| `DB_HOST` | PostgreSQL host | `db.example.com` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DJANGO_SUPERUSER_USERNAME` | Auto-created admin username | `admin` |
| `DJANGO_SUPERUSER_PASSWORD` | Auto-created admin password | — |

### Optional

| Variable | Purpose | Default |
|----------|---------|---------|
| `DEBUG` | Debug mode | `False` |
| `DB_ENGINE` | Database engine override | `django.db.backends.postgresql` |
| `DJANGO_SUPERUSER_EMAIL` | Admin email | `""` |
| `RSA_KEY_PASSPHRASE` | Passphrase for RSA key encryption at rest | Blank (required in prod) |
| `FRONTEND_URL` | Frontend domain for admin live preview links | `""` |
| `REDIS_URL` | Redis connection URL for caching | Falls back to FileBasedCache in-container; Redis is recommended for multi-instance deployments |
| `VITE_API_BASE_URL` | Backend API URL for frontend build | `/api` (dev proxy) |

### AWS S3 Storage

| Variable | Purpose | Default |
|----------|---------|---------|
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket for static/media files | `itg-static-assets` |
| `AWS_ACCESS_KEY_ID` | IAM access key (or use instance role) | — |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key | — |
| `AWS_S3_REGION_NAME` | S3 region | `us-west-2` |
| `AWS_S3_ENDPOINT_URL` | Custom S3 endpoint (for R2 etc.) | — |
| `AWS_S3_CUSTOM_DOMAIN` | CDN domain for S3 | `{bucket}.s3.amazonaws.com` |

### Email (SES)

| Variable | Purpose | Default |
|----------|---------|---------|
| `SES_AWS_ACCESS_KEY_ID` | SES IAM access key | `""` |
| `SES_AWS_SECRET_ACCESS_KEY` | SES IAM secret key | `""` |
| `SES_AWS_REGION` | SES region | `us-west-2` |
| `SES_FROM_EMAIL` | SES sender email | `i2g@g.ucmerced.edu` |
| `SES_FROM_NAME` | SES sender display name | `Innovate to Grow` |

### Google Sheets

| Variable | Purpose |
|----------|---------|
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Service account JSON (preferred) |
| `GOOGLE_SHEETS_SCOPES` | OAuth scopes (default: `spreadsheets.readonly`) |
| `GOOGLE_SHEETS_API_KEY` | API key fallback (public sheets only) |

### CORS and CSRF (Production)

| Variable | Purpose |
|----------|---------|
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins for CSRF |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed CORS origins |

---

## Production Architecture

```
                    ┌─────────────┐
     Users ──────── │  CloudFront │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
     ┌────────▼────────┐     ┌─────────▼─────────┐
     │  AWS Amplify    │     │  AWS ALB           │
     │  (Frontend)     │     │  (TLS termination) │
     │  React SPA      │     └─────────┬──────────┘
     └─────────────────┘               │
                              ┌────────▼────────┐
                              │  AWS ECS Fargate │
                              │  (Backend)       │
                              │  Gunicorn + Django│
                              └──┬─────┬────┬───┘
                                 │     │    │
                    ┌────────────┘     │    └────────────┐
                    │                  │                  │
           ┌───────▼───────┐  ┌───────▼───────┐ ┌───────▼───────┐
           │  PostgreSQL   │  │  Redis         │ │  S3           │
           │  (RDS)        │  │  (ElastiCache) │ │  (static +   │
           │               │  │                │ │   media)      │
           └───────────────┘  └───────────────┘ └───────────────┘
```

### Backend: ECS Fargate

- Docker container built from `src/Dockerfile`
- Image: Python 3.11-slim with gunicorn (3 workers, 120s timeout)
- Task: 256 CPU units, 512 MB memory
- Health check: `GET /health/` every 30 seconds

### Frontend: AWS Amplify

- Static SPA built with `npm run build` (TypeScript check + Vite build)
- Deployed via GitHub Actions after CI passes
- `VITE_API_BASE_URL` set at build time to point to the backend API domain

---

## Docker Image

The backend Dockerfile (`src/Dockerfile`) is a single-stage build:

1. Base image: `python:3.11-slim`
2. System deps: `libpq-dev` (PostgreSQL client library)
3. Python deps: installed from `src/requirements.txt`
4. Application code: copied into `/app`
5. Non-root user: `django:django`
6. Entrypoint: `/app/entrypoint.sh`
7. Default command: `gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120`

### Entrypoint Script

The entrypoint (`src/entrypoint.sh`) runs on every container start:

1. **Wait for database** — retries PostgreSQL connection up to 30 times (2s intervals)
2. **Run migrations** — `python manage.py migrate --noinput`
3. **Ensure superuser** — creates or updates the admin user from `DJANGO_SUPERUSER_*` env vars (password is always synced to support rotation)
4. **Collect static files** — `python manage.py collectstatic --noinput`
5. **Start server** — executes the CMD (gunicorn)

---

## CI/CD Pipeline

All workflows are in `.github/workflows/`.

### CI (`ci.yml`)

Triggers on push to `main` and on pull requests (when `src/`, `pages/`, `aws/`, or workflow files change).

| Stage | Job | What It Does |
|-------|-----|-------------|
| 1 | Code Style Check | Ruff (Python) + ESLint (TypeScript) via `lint.yml` |
| 2a | Django Build & Test | Install deps, migrate (SQLite), run tests, `manage.py check` |
| 2b | Docker Build Test | Build Docker image, export as artifact |
| 2c | Frontend Build | `npm ci` + `npm run build` |
| 3 | DB Migration Test | Load Docker image, run migrations against PostgreSQL 16 service container, verify no pending migrations |

### Backend Deploy (`deploy-backend.yml`)

Triggers after successful CI on `main` (or manual dispatch).

1. Build Docker image and push to Amazon ECR (tagged with git SHA + `latest`)
2. Render ECS task definition from `aws/task-definition.json` template (substitutes env vars)
3. Deploy to ECS with service stability wait
4. Verify deployment was not rolled back
5. Smoke test: curl `/health/` and verify CORS headers

### Frontend Deploy (`deploy-frontend.yml`)

Triggers after successful CI on `main` (or manual dispatch).

1. Checkout and install Node.js 20
2. `npm ci` + `npm run build` (with `VITE_API_BASE_URL` from GitHub vars/secrets)
3. Create Amplify deployment, upload zipped dist
4. Start deployment

---

## External Dependencies

| Service | Used For | Required In |
|---------|----------|------------|
| PostgreSQL | Primary database | Production |
| Redis | Cache backend | Optional (falls back to LocMemCache) |
| AWS S3 | Static and media file storage | Production |
| AWS SES | Transactional email sending | Optional (alternative to Gmail) |
| Google Sheets API | Read project/event data | Optional (for sheet-powered pages) |
| Gmail API | Email sending via service account | Optional (alternative to SES) |

---

## Security Settings (Production)

Configured in `src/core/settings/prod.py`:

- `SECURE_HSTS_SECONDS = 31536000` (1 year) with `HSTS_INCLUDE_SUBDOMAINS` and `HSTS_PRELOAD`
- `SECURE_SSL_REDIRECT = False` (ALB handles HTTP → HTTPS)
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (trusts ALB)
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`
- `X_FRAME_OPTIONS = "DENY"`
- `SECURE_SERVER_HEADER = None` (hides server version)
- `REQUIRE_ENCRYPTED_PASSWORDS = True` (blocks plaintext password submission)
- `CORS_ALLOW_CREDENTIALS = True` with explicit `CORS_ALLOWED_ORIGINS`

---

## Management Commands

| Command | App | Purpose |
|---------|-----|---------|
| `python manage.py runserver` | — | Start dev server |
| `python manage.py migrate` | — | Apply database migrations |
| `python manage.py createsuperuser` | — | Create admin user |
| `python manage.py collectstatic` | — | Collect static files for production |
| `python manage.py resetdb --force --confirm RESET_DB` | core | Reset database (dev only) |
| `python manage.py seed_initial_data` | pages | Seed menu and footer data |
| `python manage.py cms_seed` | pages | Seed CMS pages |
| `python manage.py sync_news` | news | Sync news from RSS feed sources |
| `python manage.py sync_projects` | projects | Import projects from Google Sheets |
| `python manage.py test_gmail_connection` | mail | Test Gmail API connection |
