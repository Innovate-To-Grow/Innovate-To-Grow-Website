---
name: deployment
description: Use this skill when working with Docker, CI/CD, environment settings, or deployment configuration.
---
# Deployment and Environment Configuration

## Settings Architecture

Component-based under `src/core/settings/`. Import order matters:

```
core/settings/
  base.py                          # Assembles via wildcard imports (order matters)
  dev.py                           # SQLite, DEBUG=True, console email
  ci.py                            # PostgreSQL, DEBUG=False
  prod.py                          # Imports base + production component
  components/
    framework/environment.py       # BASE_DIR, .env loading, shared env vars
    framework/django.py            # INSTALLED_APPS, middleware, templates, auth
    integrations/admin.py          # Unfold admin theme
    integrations/api.py            # DRF + SimpleJWT
    integrations/editor.py         # CKEditor 5
    production.py                  # S3, Redis, SMTP, SSL, security headers
```

Import order in `base.py`: `environment` → `django` → `admin` → `api` → `editor`.
`prod.py` adds `production` on top.

## Environment Differences

| Setting | Dev | CI | Prod |
|---|---|---|---|
| `DEBUG` | `True` | `False` | `False` |
| Database | SQLite | PostgreSQL 16 | PostgreSQL + SSL |
| Cache | LocMemCache | LocMemCache | Redis (file fallback) |
| Email | Console | Console | SMTP |
| Storage | Local filesystem | Local filesystem | S3/R2 via boto3 |
| Passwords | Plain text OK | Plain text OK | Encrypted required |
| Settings module | `core.settings.dev` | `core.settings.ci` | `core.settings.prod` |

## Backend Docker

- Dockerfile: `src/Dockerfile` (Python 3.11-slim).
- Entrypoint: `src/entrypoint.sh` — runs migrations, collectstatic, starts Gunicorn (4 workers, 2 threads, 120s timeout, port 8000).
- Deployed to ECR → ECS Fargate (512 CPU, 1024 MB).
- Task definition template: `aws/task-definition.json`.

## Frontend Build

- `npm run build` in `pages/` → `tsc -b` then `vite build`.
- Output zipped and uploaded to S3 via AWS Amplify API.
- Pure static SPA — no SSR.

## CI Pipeline (`.github/workflows/ci.yml`)

Triggers: push to main, PRs touching `src/`, `pages/`, `aws/`, `.github/workflows/`.

| Job | What it does |
|---|---|
| lint | Ruff check + format (backend), ESLint + tsc (frontend) |
| django-build | Install deps, migrate, run Django tests (PostgreSQL service) |
| backend-docker-build | Build Docker image, save as artifact |
| backend-db-migration | Validate `makemigrations --check --dry-run`, apply + `migrate --check` |
| frontend-test | `npx vitest run --reporter=verbose` |
| frontend-build | `npm ci && npm run build` |

## Deployment Workflows

- `.github/workflows/deploy-backend.yml` — Build → ECR push → ECS deploy → health check + CORS validation.
- `.github/workflows/deploy-frontend.yml` — Build → ZIP → S3 upload → Amplify deploy.

## Adding New Settings

- New integration: add a component file under `core/settings/components/integrations/`.
- Small change: add to the appropriate existing component.
- Import new components in `base.py` in the correct position.
- Environment-specific overrides go in `dev.py`, `ci.py`, or the `production.py` component.

## Environment Variables

- Prod secrets from env vars (never committed). See `src/.env.example`.
- Dev uses hardcoded defaults in `dev.py` for zero-setup.
- CI uses env vars from GitHub Actions workflow file.
- Required prod vars enforced by `_get_required_env()` in `production.py`.

## Do NOT

- Commit secrets, API keys, or production credentials.
- Change the settings import order in `base.py` without understanding dependencies.
- Edit `ci.py` database config without updating `.github/workflows/ci.yml` to match.
- Skip Docker build validation — CI catches migration and build issues.
- Modify `Dockerfile` without testing locally: `docker build -t test src/`.
- Use `prod.py` settings locally — always use `dev.py`.

## Key Files

- `src/core/settings/base.py` — settings assembly
- `src/core/settings/dev.py` — local development
- `src/core/settings/ci.py` — CI pipeline
- `src/core/settings/prod.py` — production entry
- `src/core/settings/components/production.py` — S3, Redis, SMTP, SSL
- `src/Dockerfile` — backend Docker image
- `src/entrypoint.sh` — container entrypoint
- `src/.env.example` — required environment variables
- `aws/task-definition.json` — ECS task definition template
- `.github/workflows/ci.yml` — CI pipeline
- `.github/workflows/deploy-backend.yml` — backend deployment
- `.github/workflows/deploy-frontend.yml` — frontend deployment
