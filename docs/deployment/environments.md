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
| `DJANGO_SECRET_KEY` | Django secret key. It also signs the newsletter unsubscribe links, valid for 365 days: changing it breaks every link already sent (no `SECRET_KEY_FALLBACKS` is configured) | Yes |
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
| `REDIS_URL` | Redis connection URL | No (falls back to a per-container file cache; unset in production today) |
| `SEND_VERIFICATION_MODE` | Explicit override: `observe` / `enforce` / `pause` | No (inherits active admin config; fallback `observe`) |
| `SEND_VERIFICATION_COST` | Explicit override for ALTCHA PBKDF2 cost | No (inherits active admin config; fallback 5000) |
| `SEND_VERIFICATION_SMS_DAILY_LIMIT` | Channel-wide SMS reservation cap per UTC day; while unset (and no admin value), the per-IP SMS fallback throttle applies | Required before `enforce` for SMS |

#### Production cache today

Verified from the GitHub deploy configuration: production has **no Redis**.
`REDIS_URL_SECRET_ARN` is set neither as a repository nor as an environment
variable or secret, so `deploy-backend.yml` drops the `REDIS_URL` secret when it
renders `aws/task-definition.json` (the repository variable `REDIS_URL` holds
only the placeholder `__EMPTY__` and is not read by the deploy), and
`config/settings/components/production.py` selects Django's `FileBasedCache`
under the container's temp directory (`MAX_ENTRIES` 2,000, kept small on purpose: see below). That cache is
**per container**: the Uvicorn workers in one `itg-backend` container
(`WEB_CONCURRENCY`, default 2) share it, the `itg-background-worker` container
has its own, and each ECS task has its own (the task definition mounts no shared
volume). `incr` on it is a non-atomic read-modify-write.

Nothing that bounds security or money uses it. These counters are all in
PostgreSQL: send quotas, the SMS daily budget, challenge attempt counts, the
password-login lockout for member and admin-panel sign-in (including the admin "remembered" form's own counter)
(`authn_loginfailurewindow`), and the assistant / AI-search token budgets, per
visitor or member and global (`PublicAssistantTokenBudget`, used when
`REDIS_URL` is unset; see
[Assistant and AI search limits](../integrations/assistant-limits.md)). What
still depends on the per-container cache, and is therefore per task and best
effort:

- the DRF throttles whose keys the server chooses (fairness only): the
  per-member throttles on authenticated endpoints (verification sends, project
  share and AI search, the CLI). The assistant, page-view, SMS fallback and SES
  webhook throttles are **not** here, because a caller can vary their key; see
  [The `throttle` cache alias](#the-throttle-cache-alias);
- the per-invitation attempt counter of the admin invitation page (counted only
  for an invitation that exists, so a made-up token writes nothing);
- the admin confirm-on-save pending uploads and secrets (a lost entry makes the
  confirmation fail loudly and the admin repeats the save) and CMS preview
  payloads (`cms:preview:*`, `cms:live-preview:*`; a lost one is a 404);
- the CSP-report log limiter, the once-a-minute guard on the assistant
  budget-exhausted warning, and ordinary read caches (a miss only costs a query).

With more than one task, each of these limits is effectively multiplied by the
task count (managed in AWS, not in this repository; see
[Backend deployment](backend.md#ecs-service-scaling)). Setting `REDIS_URL`
through `REDIS_URL_SECRET_ARN` would make them shared and atomic; it is not
needed for the lockout, send verification or the token budgets.

#### The `throttle` cache alias

Every settings module defines a second cache alias, `throttle`
(`THROTTLE_CACHE` in `config/settings/components/framework/cache.py`): a
`LocMemCache` with `MAX_ENTRIES` 50,000 and `CULL_FREQUENCY` 3, the same in
development, CI and production, with or without `REDIS_URL`. It holds the
history of the throttles whose **key an anonymous caller mints**, and of the
total page-view cap:

| Throttle | Endpoint | Key |
|----------|----------|-----|
| `PageViewVisitorThrottle`, `PageViewLegacyThrottle` | `POST /analytics/pageview/` | browser `visitor_id`, or one shared legacy bucket |
| `PageViewTotalThrottle` | `POST /analytics/pageview/` | one constant key: at most 3,000 page views a minute in total |
| `PublicAssistantActorThrottle` | `POST /assistant/chat/` | visitor token, member, or one shared legacy bucket |
| `PhoneAuthCodeRequestThrottle` | SMS code requests, only while no SMS daily budget is configured | client address as DRF reads it (the forgeable `X-Forwarded-For` string); a speed bump only. While it applies, enforce mode sends no SMS and observe mode is bounded only per number, so configure `sms_daily_limit` |
| `SesEventThrottle` | `POST /mail/ses/events/` | the same client address |

While `BACKGROUND_JOBS_ENABLED` is off it also holds the one-hour marker that
limits newsletter unsubscribe / resubscribe confirmation emails to one per
member and action (`mail:subscription-confirmation:*`; with the outbox the
job's dedupe key does this instead, see
[Auth & Mail](../api/auth-and-mail.md#one-click-unsubscribe-and-resubscribe)).

Why they are not in the default cache: each new key is one entry, and a script
can send a fresh `visitor_id` or visitor token with every request. In the file
cache every entry is a file, and Django lists the whole cache directory on
every write, so each cache write of the container gets slower with every
minted key (measured on a local SSD: about 1 ms per 1,000 files); at `MAX_ENTRIES` a
random third of all entries is deleted, unrelated state included. That is also
why the file cache's own `MAX_ENTRIES` is only 2,000: whatever path a junk key
comes in by, ordinary cache writes stay within a couple of milliseconds (the
write that triggers a cull takes tens of milliseconds), and nothing that bounds
security or money depends on what a cull drops. The
`throttle` alias has a hard ceiling instead: about 16 MB per process when full
of single-request keys and up to about 70 MB in the worst case (every key with
a full history), a write costs the same at any fill, and at the ceiling the
least-recently-used third is dropped, which are the flood's own stale keys
rather than the buckets in use.

What that means for the limits:

- They are **per process**. Each Uvicorn worker has its own history, so with
  `WEB_CONCURRENCY=2` a container admits up to twice each rate, each ECS task
  multiplies it again, and a restart or deploy forgets the history.
- They are fairness limiters that fail open. **Nothing that bounds security or
  money may use this alias**; those counters stay in PostgreSQL (see above).
- The total page-view cap (3,000 a minute per worker, about twenty times the
  estimated busiest campus minute) is the only one that refuses honest traffic
  when it is reached, and it only drops analytics rows: the frontend ignores
  the `429`. The worker logs `analytics.pageview_total_cap` (WARNING) at most
  once a minute while that happens.
- In development and CI the default cache is `DevelopmentLocMemCache`, whose
  `clear()` also empties the `throttle` alias, so a test's `cache.clear()`
  resets throttle history as before. A test that overrides `CACHES` must keep
  a `throttle` entry if it calls one of these endpoints: a missing alias
  raises `InvalidCacheBackendError`, it never falls back to `default`.

#### What still keys on the client IP

Campus users share one public IP, so nothing a campus user does may be limited
by it. Three limiters still use the client IP, each for a stated reason:

| Limiter | Rate | Why it remains |
|---------|------|----------------|
| `SesEventThrottle` on `POST /mail/ses/events/` | 600/minute | Callers are AWS SNS delivery addresses, never users. Authenticity comes from the SNS signature and topic allowlist; the throttle only sheds junk |
| CSP-report log limiter (`/csp-report/`) | 60 reports/minute | Detection only: the endpoint always answers `204` and only logging is skipped |
| `PhoneAuthCodeRequestThrottle` (anonymous SMS code requests) | 5/minute | Fallback only, attached while **no** SMS daily budget is configured. Setting `sms_daily_limit` removes it with no deploy ([Send verification](send-verification.md#client-ip-policy-and-residual-risks)) |

`EmailCodeVerifyThrottle` is also IP-based but is attached only to authenticated
views, where an anonymous throttle never applies. The client IP is otherwise
only recorded, never limited on: `PageView.ip_address`, the assistant log's
`ip_hash` and the CLI audit rows. The two anonymous endpoints with no
IP-independent bound on request count, `POST /analytics/pageview/` and
`POST /assistant/chat/`, get an off-campus-only rate rule at the edge
([WAF rate limits](waf-rate-limits.md), pattern set C).

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
| Cache | LocMemCache | LocMemCache | Redis if `REDIS_URL` is set, else per-container file cache (production today); plus the in-process `throttle` alias in every environment |
| Email | Console (stdout) | Console (stdout) | AWS SES / SMTP |
| File storage | Local filesystem | Local filesystem | S3 via django-storages |
| Password hashers | Plain text OK | Plain text OK | Argon2/bcrypt required |
| Debug mode | True | False | False |
| CORS | localhost:5173 | N/A | Configured origins |
| CSRF | localhost origins | N/A | Configured origins |
| SSL | No | No | Yes (via proxy) |
| HSTS | No | No | Yes |
| Secure cookies | No | No | Yes |
| Logging | Console (default) | Console | Plain-text console lines (`LEVEL time module pid tid message`) to CloudWatch Logs |

## Related pages

- [Local Development](local-development.md) — Setup with dev settings
- [Backend Deployment](backend.md) — Production backend configuration
- [CI/CD](ci-cd.md) — CI environment specifics
