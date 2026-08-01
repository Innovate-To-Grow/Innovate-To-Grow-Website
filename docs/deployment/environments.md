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
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames | Yes |
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
| `CSP_REPORT_ONLY` | Emit report-only CSP when true; enforce when false | No (defaults to true) |

### Durable jobs

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `BACKGROUND_WORKER_ENABLED` | Deploy one ECS consumer before changing web queue production | For worker deployment; defaults to the legacy queue flag |
| `BACKGROUND_JOBS_ENABLED` | Let web processes enqueue durable jobs | No (safe default `false`; requires worker flag `true`) |
| `BACKGROUND_JOB_METRICS_NAMESPACE` | Environment-isolated CloudWatch worker metrics namespace | For worker deployment |
| `BACKGROUND_WORKER_HEARTBEAT_MAX_AGE_SECONDS` | Maximum accepted heartbeat age during deploy | No (defaults to 180) |
| `BACKGROUND_WORKER_HEARTBEAT_TIMEOUT_SECONDS` | Time allowed for the heartbeat gate | No (defaults to 300) |
| `ECS_WORKER_SERVICE` | Existing ECS service updated to one consumer | For worker deployment |
| `ECS_WORKER_TASK_FAMILY` | Worker task-definition family | For worker deployment |
| `ECS_WORKER_LOG_GROUP` | Worker CloudWatch Logs group | For worker deployment |

Use distinct metrics namespaces for production and demo. Initial rollout is
`BACKGROUND_WORKER_ENABLED=true` with `BACKGROUND_JOBS_ENABLED=false`; only
turn the latter on after the deployment observes a fresh `WorkerHeartbeat`.
Both flags default off when no legacy value exists.

### AWS / Storage

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket for static/media files | Yes |
| `AWS_S3_REGION_NAME` | S3 region | Yes |
| `AWS_S3_ENDPOINT_URL` | Custom S3 endpoint (for R2 compatibility) | No |

ECS accesses S3 through `ECS_TASK_ROLE_ARN`; do not inject long-lived
`AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` values into web or worker tasks.
GitHub deployment uses a separate environment-scoped OIDC role.

### AWS services (SES, SNS, Bedrock)

A single IAM key in [`AWSCredentialConfig`](../../src/apps/core/models/base/service_credentials/aws.py) drives SES, SNS, and Bedrock. It also stores the shared AWS region, SNS origination number, and SMS OTP template. SES sender identity lives in [`EmailServiceConfig`](../../src/apps/core/models/base/service_credentials/email.py).

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `SES_CONFIGURATION_SET_NAME` | Optional SES configuration set name for campaign tagging | No |
| `SES_SNS_TOPIC_ARN` | SNS topic ARN used to validate SES bounce/complaint webhook | If using bounce webhook |

### Cache

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `REDIS_URL` | Shared Redis connection URL | When the public assistant or durable worker is enabled; optional otherwise |

### Frontend / CORS

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `FRONTEND_URL` | Frontend origin URL | Yes |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins | Yes |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS origins | Yes |
| `VITE_API_BASE_URL` | Backend API URL for frontend build | Yes (build-time) |
| `BACKEND_SMOKE_URL` | Optional direct backend URL for backend deploy smoke checks | No |
| `AMPLIFY_BACKEND_PROXY_URL` | Optional backend origin used by Amplify rewrite rules | No |
| `AMPLIFY_PROXY_ADMIN_PATHS` | Enable Amplify `/admin`, `/static`, and `/media` proxy rules | No |
| `AMPLIFY_CSP_FRAME_SOURCES` | Exact/wildcard HTTPS iframe origins allowed by deployed CSP | Yes for frontend deploy |
| `AMPLIFY_CSP_MODE` | `report-only` during observation, then `enforce` | No (defaults to `report-only`) |

### Production targets

The `Deploy Production` workflow places every selected component behind one
`Production Deployments` approval gate. Component jobs then use separate GitHub
Environment targets for production and demo variables, secrets, URLs, and
deployment history. The demo target is intended to use isolated backend data
and deployment resources while sharing the same source code and container
image.

| GitHub Environment | Purpose |
|--------------------|---------|
| `Production Deployments` | Required-reviewer gate that approves the complete normal deployment set once |
| `AWS ECS - Prod` | Existing production backend |
| `AWS ECS(DEMO) - Prod` | Demo backend, default admin URL `https://demo.i2g.ucmerced.edu/admin` |
| `AWS Amplify - Prod` | Existing production frontend |
| `AWS Amplify(DEMO) - Prod` | Demo frontend, default URL `https://demo.i2g.ucmerced.edu` |

After the shared gate is active on `main`, configure required reviewers only
on `Production Deployments`, not on each AWS target environment. A target with
its own required reviewers creates an additional approval card. Keep the
target environments because jobs can read their environment-scoped variables
and secrets only when they reference those environments.

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
S3 values above. Reuse the existing OIDC deployment role plus secret ARN
variables for `DJANGO_SECRET_KEY`, `DB_PASSWORD`, and the create-only
`DJANGO_SUPERUSER_PASSWORD` input unless separate demo credentials are
intentionally created.

### Google Sheets

Google service-account credentials live in [`GoogleCredentialConfig`](../../src/apps/core/models/base/service_credentials/google.py) in the database. Paste the service-account JSON into Django admin → Site Settings → Google Credential Configs. No process env vars are required.

### Database-managed credentials

These integrations read credentials from Django admin → Site Settings at runtime, **not** from process env:

| Model | Purpose |
|-------|---------|
| `AWSCredentialConfig` | Shared AWS IAM key + region + SMS origination number + OTP template |
| `EmailServiceConfig` | Explicitly active SES sender identity and campaign rate |
| `GoogleCredentialConfig` | Google service-account JSON for Sheets |

Before removing legacy env vars from a deployed environment, run `python manage.py verify_service_configs --strict` against the prod DB to confirm active rows exist. See [CMS & Admin → Operations](../cms-admin/operations.md#service-configuration).

### Security

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `RSA_KEY_PASSPHRASE` | Passphrase for RSA key encryption | Recommended |
| `ENSURE_DEFAULT_ADMIN` | Run the explicit create-only demo admin one-off | No (defaults true only for demo) |
| `DJANGO_SUPERUSER_EMAIL` | Email used only by that one-off | When the one-off is enabled |
| `DJANGO_SUPERUSER_PASSWORD_SECRET_ARN` | Secret reference used only by that one-off | When the one-off is enabled |

Normal web and worker startup never creates or updates an administrator.
`ensure_default_admin --yes` runs as an explicit one-off after migration and
will not reset, reactivate, or promote an existing account.

## Feature comparison

| Feature | Dev | CI | Prod |
|---------|-----|-----|------|
| Database | SQLite | PostgreSQL 16 | PostgreSQL + SSL |
| Cache | LocMemCache | LocMemCache | Redis; required when the public assistant is enabled |
| Email | Console for Django-native dev mail | Console for Django-native test mail | AWS SES |
| Durable jobs | In-process fallback by default | PostgreSQL outbox tests | PostgreSQL outbox + ECS worker |
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
