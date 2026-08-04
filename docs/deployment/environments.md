# Environments

Configuration differences across development, CI, and production.

## Settings files

| Environment | Settings module | Database | Triggered by |
|-------------|----------------|----------|-------------|
| Local development | `config.settings.local` | SQLite | `manage.py runserver` (default) |
| CI | `config.settings.test` | PostgreSQL 16 (GH Actions service) | GitHub Actions workflow |
| Production | `config.settings.production` | PostgreSQL + SSL | ECS task environment variables |

All three extend `config.settings.base`, which wildcard-imports from `config/settings/components/`.

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
| `BACKGROUND_JOBS_ENABLED` | Queue durable background work, including Amplify route reconciliation | No (defaults to false) |
| `BACKGROUND_JOB_METRICS_NAMESPACE` | Optional CloudWatch namespace for worker heartbeat/queue metrics | No (empty disables publishing) |

### AWS / Storage

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket for static/media files | Yes |
| `AWS_S3_REGION_NAME` | S3 region | Yes |
| `AWS_ACCESS_KEY_ID` | S3 access key | Yes |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key | Yes |
| `AWS_S3_ENDPOINT_URL` | Custom S3 endpoint (for R2 compatibility) | No |

### AWS services (SES, SNS, Bedrock)

A single IAM key in [`AWSCredentialConfig`](../../src/apps/core/models/base/service_credentials/aws.py) drives SES, SNS, and Bedrock. It also stores the shared AWS region, SNS origination number, and SMS OTP template. SES sender identity lives in [`EmailServiceConfig`](../../src/apps/core/models/base/service_credentials/email.py).

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
| `BACKEND_SMOKE_URL` | Optional direct backend URL for backend deploy smoke checks | No |
| `AMPLIFY_BACKEND_PROXY_URL` | Backend origin used by the canonical Amplify rewrite rules | Yes when `AMPLIFY_APP_ID` is set |
| `AMPLIFY_PROXY_ADMIN_PATHS` | Enable Amplify `/admin`, `/static`, and `/media` proxy rules | No |
| `AMPLIFY_APP_ID` | Amplify app whose edge rules receive active CMS route redirects | Required for edge 301 sync |
| `AMPLIFY_CONFIG_REVISION` | Monotonic backend deployment generation (`<run_id>.<run_attempt>`) used to order Amplify configurations | Injected automatically by deployment |

Route-redirect synchronization uses the ECS task role through boto3's ambient credentials. Scope that role to `amplify:GetApp` and `amplify:UpdateApp` for the environment's specific Amplify app ARN; do not reuse the database-managed SES/SNS credentials for this operation. The backend worker is the only repository-managed writer of the full Amplify custom-rule list; it reconciles the sitemap, API, optional admin/static/media proxies, CMS 301s, and final SPA fallback while preserving unrelated rules. The frontend deploy workflow publishes assets only and must not call `UpdateApp`. Without the app ID, IAM permission, or an enabled background worker, the existing CMS SPA fallback remains available and the admin reports edge synchronization as pending or failed.

The backend deployment defaults `AMPLIFY_BACKEND_PROXY_URL` to the target's
direct API origin (`api.i2g.ucmerced.edu` for production and
`demo-api.i2g.ucmerced.edu` for demo) and defaults admin-path proxying to false
for production and true for demo. Set the same values in each target's ECS
GitHub Environment if overriding them. `AMPLIFY_CONFIG_REVISION` is stamped by
the workflow from GitHub's numeric run ID and attempt; do not define or override
it in a GitHub Environment. If `BACKGROUND_JOB_METRICS_NAMESPACE`
is enabled, also grant the task role `cloudwatch:PutMetricData`; leaving it
empty avoids that permission and does not affect job processing.

### Production targets

The deploy workflows run separate GitHub Environment targets for production and
demo. The demo target is intended to use isolated backend data and deployment
resources while sharing the same source code and container image.

| GitHub Environment | Purpose |
|--------------------|---------|
| `Production Deployments` | Single required-reviewer gate shared by every production deployment |
| `AWS ECS - Prod` | Existing production backend |
| `AWS ECS(DEMO) - Prod` | Demo backend, default admin URL `https://demo.i2g.ucmerced.edu/admin` |
| `AWS Amplify - Prod` | Existing production frontend |
| `AWS Amplify(DEMO) - Prod` | Demo frontend, default URL `https://demo.i2g.ucmerced.edu` |
| `AWS ECS - Archive Prod` | Archived event-pages ECS service |

Keep required reviewers on `Production Deployments`. The five target
environments continue to provide target-specific variables, secrets, URLs, and
deployment history, but must not also require reviewers after the unified gate
has been verified; otherwise GitHub requests a second approval.

### Demo target values

The demo site is deployed as a separate frontend, backend service, static asset
bucket, and PostgreSQL database. To keep demo cost low, the demo database is a
separate logical database on the existing RDS instance, not a second RDS
instance.

| Setting | Value |
|---------|-------|
| Frontend URL | `https://demo.i2g.ucmerced.edu` |
| Admin URL | `https://demo.i2g.ucmerced.edu/admin` |
| Direct backend origin | `https://demo-api.i2g.ucmerced.edu` |
| Amplify app id | `d216f5mwm2zgtd` |
| Amplify branch | `main` |
| ECS cluster | `itg-backend-cluster` |
| ECS service | `itg-backend-demo-service` |
| ECS task family | `itg-backend-demo` |
| ECS log group | `/ecs/itg-backend-demo` |
| Database host | `i2g-prod-postgres-west2.cerh6zqru5na.us-west-2.rds.amazonaws.com` |
| Database name | `innovate_to_grow_demo` |
| S3 static/media bucket | `itg-demo-static-assets` |

Configure `AWS Amplify(DEMO) - Prod` with `AMPLIFY_APP_ID=d216f5mwm2zgtd`,
`AMPLIFY_BRANCH=main`, `FRONTEND_URL=https://demo.i2g.ucmerced.edu`,
`VITE_API_BASE_URL=https://demo.i2g.ucmerced.edu/api`,
`AMPLIFY_BACKEND_PROXY_URL=https://demo-api.i2g.ucmerced.edu`, and
`AMPLIFY_PROXY_ADMIN_PATHS=true`.

Configure `AWS ECS(DEMO) - Prod` with the ECS, database, URL, CORS/CSRF, and
S3 values above. Reuse the existing deployment AWS credentials and secret ARN
variables for `DJANGO_SECRET_KEY`, `DB_PASSWORD`, and
`DJANGO_SUPERUSER_PASSWORD` unless separate demo credentials are intentionally
created.

### Google Sheets

Google service-account credentials live in [`GoogleCredentialConfig`](../../src/apps/core/models/base/service_credentials/google.py) in the database. Paste the service-account JSON into Django admin → Site Settings → Google Credential Configs. No process env vars are required.

### Database-managed credentials

These integrations read credentials from Django admin → Site Settings at runtime, **not** from process env:

| Model | Purpose |
|-------|---------|
| `AWSCredentialConfig` | Shared AWS IAM key + region + SMS origination number + OTP template |
| `EmailServiceConfig` | Sender identity, campaign rate, SMTP fallback |
| `GoogleCredentialConfig` | Google service-account JSON for Sheets |

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
