# Deployment & Infrastructure Guide

This guide covers the production infrastructure, Docker setup, CI/CD pipeline, and environment configuration.

## Infrastructure Overview

```
                    ┌─────────────────┐
                    │   GitHub Actions │
                    │   (CI/CD)        │
                    └───────┬─────────┘
                            │
               ┌────────────┼────────────┐
               ▼                         ▼
    ┌──────────────────┐     ┌───────────────────┐
    │  AWS ECR          │     │  AWS Amplify       │
    │  (Docker images)  │     │  (Frontend SPA)    │
    └────────┬─────────┘     └───────────────────┘
             │
             ▼
    ┌──────────────────┐
    │  ECS Fargate      │
    │  (Django + Gunicorn)│
    │  Cluster: itg-backend-cluster │
    │  Service: itg-backend-service │
    └────────┬─────────┘
             │
    ┌────────┼─────────────────┐
    │        │                 │
    ▼        ▼                 ▼
┌────────┐ ┌────────┐ ┌──────────────┐
│ RDS    │ │ Redis  │ │ S3           │
│ Postgres│ │ (opt.) │ │ static/media │
└────────┘ └────────┘ └──────────────┘
```

| Service | AWS Product | Purpose |
|---------|------------|---------|
| Backend | ECS Fargate | Django app with Gunicorn (3 workers, 120s timeout) |
| Frontend | Amplify | React SPA static hosting |
| Database | RDS PostgreSQL 16 | Primary data store (SSL required) |
| Cache | ElastiCache Redis | Page/layout caching (optional, falls back to LocMemCache) |
| Storage | S3 (`itg-static-assets`) | Static files (`/static/`) and media uploads (`/media/`) |
| CDN | CloudFront | Serves backend and static assets |
| Container Registry | ECR (`itg-backend`) | Docker image storage |

## Docker Setup

### Dockerfile (`src/Dockerfile`)

Multi-stage build based on `python:3.11-slim`:

1. Install system dependencies (`libpq-dev` for PostgreSQL)
2. Install Python dependencies from `requirements.txt`
3. Copy application code
4. Create non-root `django` user
5. Expose port 8000
6. Run `entrypoint.sh` then Gunicorn

### Entrypoint Sequence (`src/entrypoint.sh`)

The entrypoint script runs these steps in order before starting the app server:

1. **Wait for database** — Retries PostgreSQL connection up to 30 times (2s intervals)
2. **Run migrations** — `python manage.py migrate --noinput`
3. **Ensure superuser** — Creates or updates the superuser from environment variables (`DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_EMAIL`). Always syncs the password from env to support rotation on deploy.
4. **Collect static files** — `python manage.py collectstatic --noinput` (uploads to S3 in production)
5. **Start server** — Executes the CMD (`gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120`)

## CI/CD Pipeline

### Overview

```
Push to main
      │
      ▼
┌──────────┐
│   CI     │ (.github/workflows/ci.yml)
│          │
│  lint ──▶ django-build (test + check)
│       ──▶ backend-docker-build ──▶ backend-db-migration (PostgreSQL)
│       ──▶ frontend-build (npm ci + build)
└────┬─────┘
     │ on success
     ├──────────────────────┐
     ▼                      ▼
┌────────────────┐  ┌─────────────────┐
│ Deploy Backend │  │ Deploy Frontend │
│ (ECS)          │  │ (Amplify)       │
└────────────────┘  └─────────────────┘
```

### CI Workflow (`.github/workflows/ci.yml`)

Triggered on pushes to `main` and all pull requests.

| Job | Depends On | What It Does |
|-----|-----------|--------------|
| **lint** | — | Runs code style checks (reusable workflow) |
| **django-build** | lint | Python 3.11, `pip install`, `migrate`, `test`, `check` |
| **backend-docker-build** | lint | Builds Docker image, saves as artifact |
| **backend-db-migration** | lint + docker-build | Runs migrations against PostgreSQL 16, verifies no pending migrations |
| **frontend-build** | lint | Node 20, `npm ci`, `npm run build` |

### Deploy Backend (`.github/workflows/deploy-backend.yml`)

Triggered when CI completes successfully on `main`, or via manual dispatch.

1. **Build Docker image** — Tags with git SHA and `latest`, pushes to ECR
2. **Validate config** — Checks that required secrets (`DJANGO_SECRET_KEY`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) are set
3. **Render task definition** — Populates `aws/task-definition.json` template with environment variables
4. **Deploy to ECS** — Uses `amazon-ecs-deploy-task-definition`, waits for service stability
5. **Smoke test** — Hits `/health/` endpoint, verifies `200` response and CORS headers

### Deploy Frontend (`.github/workflows/deploy-frontend.yml`)

Triggered when CI completes successfully on `main`, or via manual dispatch.

1. **Build** — `npm ci && npm run build` with `VITE_API_BASE_URL` env var
2. **Deploy** — Creates Amplify deployment, zips `dist/`, uploads via pre-signed URL, starts deployment

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | (random string) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `api.innovatetogrow.com,.cloudfront.net` |
| `DB_NAME` | PostgreSQL database name | `innovate_to_grow` |
| `DB_USER` | PostgreSQL username | `itg_user` |
| `DB_PASSWORD` | PostgreSQL password | (secret) |
| `DB_HOST` | PostgreSQL host | `itg-db.xxx.us-west-2.rds.amazonaws.com` |
| `DB_PORT` | PostgreSQL port | `5432` |

### AWS

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket for static/media | `itg-static-assets` |
| `AWS_S3_REGION_NAME` | S3 bucket region | `us-west-2` |
| `AWS_ACCESS_KEY_ID` | IAM access key (set as GitHub secret) | — |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key (set as GitHub secret) | — |

### Email

| Variable | Description | Default |
|----------|-------------|---------|
| `EMAIL_HOST` | SMTP server | `smtp.gmail.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_HOST_USER` | SMTP username | — |
| `EMAIL_HOST_PASSWORD` | SMTP password | — |
| `DEFAULT_FROM_EMAIL` | Sender address | `i2g@g.ucmerced.edu` |

### CORS & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins | Auto-derived from `FRONTEND_URL` and `API_BASE_URL` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS origins | Auto-derived from `FRONTEND_URL` |
| `FRONTEND_URL` | Frontend URL for CORS and preview links | — |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_ENGINE` | Database engine | `django.db.backends.postgresql` |
| `REDIS_URL` | Redis connection URL | (empty — uses LocMemCache) |
| `DJANGO_SUPERUSER_USERNAME` | Auto-created superuser username | — |
| `DJANGO_SUPERUSER_PASSWORD` | Auto-created superuser password | — |
| `DJANGO_SUPERUSER_EMAIL` | Auto-created superuser email | — |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Service account JSON (single-line) | — |
| `GOOGLE_SHEETS_SCOPES` | Comma-separated OAuth scopes | `https://www.googleapis.com/auth/spreadsheets.readonly` |
| `VITE_API_BASE_URL` | Backend API URL for the frontend build | `/api` |

### Frontend-Only (Build Time)

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | API base URL baked into the frontend build | `/api` |
| `VITE_BACKEND_URL` | Backend URL for Vite dev proxy | `http://localhost:8000` |

## Production Security Settings

Configured in `src/core/settings/prod.py`:

| Setting | Value | Notes |
|---------|-------|-------|
| `SECURE_BROWSER_XSS_FILTER` | `True` | X-XSS-Protection header |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | X-Content-Type-Options header |
| `SECURE_HSTS_SECONDS` | `31536000` (1 year) | Strict-Transport-Security |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | HSTS for subdomains |
| `SECURE_HSTS_PRELOAD` | `True` | HSTS preload list |
| `SECURE_SSL_REDIRECT` | `False` | SSL termination handled by ALB |
| `SECURE_PROXY_SSL_HEADER` | `X-Forwarded-Proto: https` | Trust ALB's SSL header |
| `SESSION_COOKIE_SECURE` | `True` | HTTPS-only session cookies |
| `CSRF_COOKIE_SECURE` | `True` | HTTPS-only CSRF cookies |
| `X_FRAME_OPTIONS` | `DENY` | Prevents framing |
| `CORS_ALLOW_CREDENTIALS` | `True` | Allows cookies in CORS requests |

## Database

- **Production**: PostgreSQL on RDS with SSL (`sslmode=require`)
- **Development**: SQLite (`src/db.sqlite3`)
- **CI**: PostgreSQL 16 service container

Migrations run automatically on deploy via `entrypoint.sh`.
