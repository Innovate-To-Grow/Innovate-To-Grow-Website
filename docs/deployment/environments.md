# Environments

Configuration differences across development, CI, and production.

## Settings files

| Environment | Settings module | Database | Triggered by |
|-------------|----------------|----------|-------------|
| Local development | `core.settings.dev` | SQLite | `manage.py runserver` (default) |
| CI | `core.settings.ci` | PostgreSQL 16 (GH Actions service) | GitHub Actions workflow |
| Production | `core.settings.prod` | PostgreSQL + SSL | ECS task environment variables |

All three extend `core.settings.base`, which wildcard-imports from `core/settings/components/`.

## Environment variable reference

Variables are loaded from `src/.env` locally and injected via ECS task definition in production.

### Django core

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `DJANGO_SECRET_KEY` | Django secret key | Yes |
| `DJANGO_SETTINGS_MODULE` | Settings module path | Yes |
| `ALLOWED_HOSTS` | Comma-separated hostnames | Yes |
| `DEBUG` | Debug mode (never `True` in prod) | No (defaults to `False`) |

### Database

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `DB_ENGINE` | Database backend (defaults to PostgreSQL) | No |
| `DB_NAME` | Database name | Yes |
| `DB_USER` | Database user | Yes |
| `DB_PASSWORD` | Database password | Yes |
| `DB_HOST` | Database host | Yes |
| `DB_PORT` | Database port | No (defaults to 5432) |
| `DB_CONN_MAX_AGE` | Django persistent DB connection lifetime in seconds | No (defaults to 0) |
| `DB_CONN_HEALTH_CHECKS` | Enable Django persistent connection health checks | No (defaults to true) |

### Backend runtime

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `WEB_CONCURRENCY` | Uvicorn worker count | No (defaults to 2) |
| `UVICORN_LIMIT_CONCURRENCY` | Uvicorn per-process concurrency cap | No (defaults to 20) |

### AWS / Storage

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket for static/media files | Yes |
| `AWS_S3_REGION_NAME` | S3 region | Yes |
| `AWS_ACCESS_KEY_ID` | S3 access key | Yes |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key | Yes |
| `AWS_S3_ENDPOINT_URL` | Custom S3 endpoint (for R2 compatibility) | No |

### Email (AWS SES)

SES credentials live in [`EmailServiceConfig`](../../src/core/models/base/service_credentials/email.py) in the database, not in process env. Configure via Django admin → Site Settings → Email Service Configs.

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `SES_CONFIGURATION_SET_NAME` | Optional SES configuration set name for campaign tagging | No |
| `SES_SNS_TOPIC_ARN` | SNS topic ARN used to validate SES bounce/complaint webhook | If using bounce webhook |

### Cache

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `REDIS_URL` | Redis connection URL | No (falls back to file cache) |

### Frontend / CORS

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `FRONTEND_URL` | Frontend origin URL | Yes |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins | Yes |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS origins | Yes |
| `VITE_API_BASE_URL` | Backend API URL for frontend build | Yes (build-time) |

### Google Sheets

Google service-account credentials live in [`GoogleCredentialConfig`](../../src/core/models/base/service_credentials/google.py) in the database. Paste the service-account JSON into Django admin → Site Settings → Google Credential Configs. No process env vars are required.

### Database-managed credentials

These integrations read credentials from Django admin → Site Settings at runtime, **not** from process env:

| Model | Purpose |
|-------|---------|
| `EmailServiceConfig` | AWS SES + SMTP fallback |
| `SMSServiceConfig` | AWS SNS phone verification |
| `GoogleCredentialConfig` | Google service-account JSON for Sheets |
| `AWSCredentialConfig` | Shared AWS IAM keys (SNS, Bedrock) |

Before removing legacy env vars from a deployed environment, run `python manage.py verify_service_configs --strict` against the prod DB to confirm active rows exist. See [CMS & Admin → Operations](../cms-admin/operations.md#service-configuration).

### Security

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `RSA_KEY_PASSPHRASE` | Passphrase for RSA key encryption | Recommended |
| `DJANGO_SUPERUSER_EMAIL` | Initial superuser email (ECS startup) | No |
| `DJANGO_SUPERUSER_PASSWORD` | Initial superuser password (ECS startup) | No |

## Feature comparison

| Feature | Dev | CI | Prod |
|---------|-----|-----|------|
| Database | SQLite | PostgreSQL 16 | PostgreSQL + SSL |
| Cache | LocMemCache | LocMemCache | Redis (file fallback) |
| Email | Console (stdout) | Console (stdout) | AWS SES / SMTP |
| File storage | Local filesystem | Local filesystem | S3 via django-storages |
| Password hashers | Plain text OK | Plain text OK | Argon2/bcrypt required |
| Debug mode | True | False | False |
| CORS | localhost:5173 | N/A | Configured origins |
| CSRF | localhost origins | N/A | Configured origins |
| SSL | No | No | Yes (via proxy) |
| HSTS | No | No | Yes |
| Secure cookies | No | No | Yes |
| Logging | Console (default) | Console | Structured JSON to CloudWatch |

## Related pages

- [Local Development](local-development.md) — Setup with dev settings
- [Backend Deployment](backend.md) — Production backend configuration
- [CI/CD](ci-cd.md) — CI environment specifics
