# Environments

Configuration differences across development, CI, and production.

## Settings files

| Environment | Settings module | Database | Triggered by |
|-------------|----------------|----------|-------------|
| Local development | `config.settings.environments.local` | SQLite | `manage.py runserver` (default) |
| CI | `config.settings.environments.test` | PostgreSQL 16 (GH Actions service) | GitHub Actions workflow |
| Production | `config.settings.environments.production` | PostgreSQL + SSL | ECS task environment variables |

All three extend `config.settings.base`, which wildcard-imports from `config/settings/base/framework/` and `config/settings/base/integrations/`. Production then applies `config/settings/production/`.

## Environment variable reference

Variables are loaded from `src/.env` locally and injected via ECS task definition in production.

### Django core

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `DJANGO_SECRET_KEY` | Django secret key. It also signs the newsletter unsubscribe links, valid for 365 days: changing it breaks every link already sent (no `SECRET_KEY_FALLBACKS` is configured) | Yes |
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
| `NUM_PROXIES` | Trusted reverse-proxy hops in front of uvicorn (the ALB is 1); must be ≥ 1. Drives per-IP throttle identity — see [Client IP and proxy trust](backend.md#client-ip-and-proxy-trust) | No (defaults to 1; deploy renders the `NUM_PROXIES` AWS deployment setting, default `1`) |
| `BACKGROUND_JOBS_ENABLED` | Queue durable background work, including Amplify route reconciliation | Enabled in production through `itg/backend/deploy-config`; code defaults to false |
| `BACKGROUND_JOB_METRICS_NAMESPACE` | Optional CloudWatch namespace for worker heartbeat/queue metrics | No (empty disables publishing) |

### AWS / Storage

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket for static/media files | Yes |
| `AWS_S3_REGION_NAME` | S3 region | Yes |
| ECS task role | Temporary S3 credentials provided by AWS | Yes; no static access key needed |
| `AWS_S3_ENDPOINT_URL` | Custom S3 endpoint (for R2 compatibility) | No |

### AWS services (SES, SNS, Bedrock)

A Secrets Manager object referenced by [`AWSCredentialConfig`](../../src/apps/core/models/base/service_credentials/aws.py) supplies the shared IAM key for SES, SNS, Bedrock, and usage metrics. Production resolves the object using the ECS task role and refuses database plaintext fallback. The database stores only the secret ARN and service metadata. It also stores the shared AWS region, SNS origination number, and SMS OTP template. The email sender identity and the selected email provider (AWS SES, SMTP, or Microsoft Graph) live in [`EmailServiceConfig`](../../src/apps/core/models/base/service_credentials/email.py).

The SES variables below matter only while AWS SES is the selected email provider.

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `SES_CONFIGURATION_SET_NAME` | Optional SES configuration set name for campaign tagging | No |
| `SES_SNS_TOPIC_ARN` | SNS topic ARN used to validate SES bounce/complaint webhook | If using bounce webhook |

### Microsoft Graph (email)

The Microsoft Graph email provider has no environment variables. Its Entra tenant ID, client ID, sender mailbox and mailbox scope live in [`MicrosoftGraphProviderConfig`](../../src/apps/core/models/base/service_credentials/microsoft_graph.py) and are entered on the Graph configuration's admin page (`/admin/core/microsoftgraphproviderconfig/`, Core app); Mail → Notification Delivery only selects Graph and shows the configuration read-only. It authenticates with a certificate only (no client secret) whose private key is kept in the credential store: the Secrets Manager secret `itg/backend/microsoft-graph/certificate-key` in production, written by the backend's task role ([Production](production.md#microsoft-graph-certificate-key)). The database keeps only the certificate's public data and the pinned version (`MicrosoftGraphCertificate`). The other deployment requirement is outbound HTTPS (port 443) from the backend and background-worker containers to `login.microsoftonline.com` and `graph.microsoft.com`; the provider connects to them directly and ignores proxy environment variables. Setup and limits: [Microsoft Graph email](../integrations/microsoft-graph-email.md).

These Django settings (not environment variables) bound the certificate, the access check and the key store. The defaults are in `config/settings/base/integrations/microsoft_graph/` and `config/settings/base/integrations/credential_store/`; the production values come from `config/settings/production/django.py`, and the test values from `config/settings/environments/test.py` (and `local.py` under `manage.py test`). The `core` system checks (`core.E001`–`core.E007`, `apps/core/checks.py`) stop every management command, container start-up included, when one is invalid.

| Setting | Default | Production | Purpose |
|---------|---------|------------|---------|
| `CREDENTIAL_STORE_BACKEND` | `local_file` (`memory` in tests) | `secretsmanager` | Where private keys are kept: a 0600 file store, process memory, or AWS Secrets Manager |
| `CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER` | `False` | `True` | Refuse to start (`core.E002`) with any store other than Secrets Manager |
| `CREDENTIAL_STORE_LOCAL_DIR` | `src/data/credential-store` | not used | Directory of the local file store (gitignored, excluded from the image); throwaway keys only |
| `CREDENTIAL_STORE_SECRETS` | `{"microsoft_graph_certificate_key": "itg/backend/microsoft-graph/certificate-key", "gmail_api_service_account_key": "itg/backend/gmail-api/service-account-key"}` | same | Logical name → secret name; a name inside `itg/backend/aws-credentials/` is refused (`core.E003`) |
| `CREDENTIAL_STORE_STAGED_LABEL` | `I2G-STAGED` | same | Staging label of a newly written version; it must not start with `AWS` (`core.E004`) |
| `CREDENTIAL_STORE_AWS_REGION`, `CREDENTIAL_STORE_AWS_ACCOUNT_ID` | `us-west-2`, `394167325273` | same | Region of the secret, and the account its ARN must belong to |
| `CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS`, `CREDENTIAL_STORE_READ_TIMEOUT_SECONDS`, `CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS` | `3`, `5`, `3` | same | Secrets Manager timeouts, and attempts including the first |
| `CREDENTIAL_STORE_MAX_PAYLOAD_BYTES` | `65536` | same | Largest stored payload (Secrets Manager's own limit) |
| `GRAPH_REQUEST_TIMEOUT_SECONDS` | `30` | same | Timeout of each token, `sendMail` and admin-inbox request |
| `GRAPH_MAX_RESPONSE_BYTES` | `65536` | same | Most of a token or `sendMail` answer (and of each access-check folder or list probe) that is read |
| `GRAPH_INBOX_LIST_MAX_BYTES`, `GRAPH_INBOX_MESSAGE_MAX_BYTES`, `GRAPH_INBOX_MAX_LIST_LIMIT` | `2097152`, `26214400`, `100` | same | Admin inbox: largest message list and raw message read, and most messages per list |
| `GRAPH_MAX_RETRY_AFTER_SECONDS` | `3600` | same | Longest `Retry-After` taken from Microsoft; a longer one is capped |
| `GRAPH_TOKEN_EXPIRY_MARGIN_SECONDS`, `GRAPH_TOKEN_MAX_LIFETIME_SECONDS` | `300`, `86400` | same | An access token is reused until this long before it expires, and a longer `expires_in` is not believed |
| `GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS` | `300` | same | Lifetime of each signed client assertion (Microsoft: 5–10 minutes at most) |
| `GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS` | `2048` | same | Smallest RSA key the Install page accepts |
| `GRAPH_CERTIFICATE_MAX_INPUT_BYTES` | `65536` | same | Largest certificate, key or `.p12` input |
| `GRAPH_CERTIFICATE_CLOCK_SKEW_SECONDS` | `300` | same | How far in the future a certificate's validity may start and still count as valid |
| `GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS` | `10` | same | Timeout of the Entra token test before an install or rollback |
| `GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`, `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS` | `60`, `14` | same | Expiry badge, worker warning and `verify_service_configs --strict` thresholds |
| `GRAPH_APPROVED_APPLICATION_ROLES` | `("Mail.Send", "Mail.Read")` | same | Application permissions InfoSec approved; any other role in the token fails the access check (`core.E006` checks the list) |
| `GRAPH_ACCESS_CHECK_TIMEOUT_SECONDS`, `GRAPH_ACCESS_CHECK_MIME_MAX_BYTES` | `10`, `4096` | same | Timeout of each access-check request, and how much raw MIME the `value` probe reads |
| `GRAPH_ACCESS_CHECK_MAX_ROLES` | `64` | same | A token claiming more roles than this counts as unreadable, so the run is not a complete validation |
| `GRAPH_REQUIRE_ACCESS_EVIDENCE` | `False` | `True` | Go-live gate: email can switch to Graph, or move to another Graph configuration once on it, only with a recorded, passing access check for that configuration's current certificate (`core.E007` checks it is a boolean) |
| `GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS` | `30` | same | Oldest access check the gate accepts |

Every number above must be positive (`core.E005`), except the clock skew, which may be `0`.

### Gmail API (email)

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `GMAIL_API_OVERRIDES` | JSON object of `GMAIL_API` keys to replace, e.g. `{"request_timeout_seconds": 20}` | No (empty keeps the defaults) |

The Gmail API provider's service account, key facts and account allow-list live in `GmailApiProviderConfig` and are managed on its admin page by superusers (`/admin/core/gmailapiproviderconfig/`); Mail → Notification Delivery only selects it. The service-account key is kept in the credential store (`CREDENTIAL_STORE_SECRETS["gmail_api_service_account_key"]`: the Secrets Manager secret `itg/backend/gmail-api/service-account-key` in production, created empty by `aws/cicd/identity-stack.json` and written by the task role), never in the database or the environment, and `seed_service_configs` never seeds it. The backend and worker need outbound HTTPS to `oauth2.googleapis.com` and `gmail.googleapis.com`; proxy variables are ignored.

`GMAIL_API` (`config/settings/base/integrations/gmail_api/`, each value with its source) holds: `request_timeout_seconds` (15), `max_response_bytes` (65536), `max_recipients_per_message` (500, Google's limit), `max_message_bytes` (25,000,000, Google's limit before encoding), `upload_max_bytes` (36,700,160, the upload endpoint's maximum), `assertion_lifetime_seconds` (300; Google allows at most 3600), `token_max_lifetime_seconds` (3600), `token_expiry_margin_seconds` (300), `key_max_input_bytes` (16384), `min_rsa_key_bits` (2048), `key_check_timeout_seconds` (10) and `access_check_timeout_seconds` (10). The recipients and size values seed the config's fields and are their ceilings. Only existing keys can be overridden, with whole numbers; an assertion lifetime above 3600, a token margin not below the token lifetime, or a size above the upload maximum raises `ImproperlyConfigured` when settings load.

### Delivery rates

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `DELIVERY_RATES_OVERRIDES` | JSON object deep-merged into the `DELIVERY_RATES` setting, e.g. `{"channels": {"sms_send": {"provider_limit": 20}}}` after an AWS quota increase | No (empty keeps the defaults) |

`DELIVERY_RATES` (`config/settings/base/integrations/delivery_rates/`) holds every delivery channel's seeds: Microsoft Graph send and read, Amazon SES, SMTP, Gmail IMAP, the Gmail API and AWS SMS. Each one has a Smart rate switch (on by default), a manual rate and the provider's documented limits, each with its source. It also holds the Smart rate controller, the send waits, the campaign lane share and transactional reserve, the usage buckets, provider discovery, background-job retries and the provider error patterns. Each channel's `DeliveryRatePolicy` row is seeded from it. A documented limit there is also a ceiling: mail staff can lower it on the policy, never raise it, so a provider that grants more is reflected here. An override can only replace settings that exist. The merged result is validated when settings load, and an unknown key, a fraction outside (0, 1], a count below 1, a worker wait not below the 600 s stale-claim recovery, or an inline wait not below the inline request budget raises `ImproperlyConfigured`, which stops every process before it starts.

### Cache

| Variable | Purpose | Required in prod |
|----------|---------|-----------------|
| `REDIS_URL` | Redis connection URL | No (falls back to a per-container file cache; unset in production today) |
| `SEND_VERIFICATION_MODE` | Explicit override: `observe` / `enforce` / `pause` | No (inherits active admin config; fallback `observe`) |
| `SEND_VERIFICATION_COST` | Explicit override for ALTCHA PBKDF2 cost | No (inherits active admin config; fallback 5000) |
| `SEND_VERIFICATION_SMS_DAILY_LIMIT` | Channel-wide SMS reservation cap per UTC day; while unset (and no admin value), the per-IP SMS fallback throttle applies | Required before `enforce` for SMS |

#### Production cache today

Verified from the deployment configuration: production has **no Redis**.
`REDIS_URL_SECRET_ARN` is absent from `itg/backend/deploy-config`, so
`deploy-backend.yml` drops the `REDIS_URL` secret when it renders the task
definition. The migrated `REDIS_URL=__EMPTY__` placeholder is retained only
as historical configuration and is not injected into the container. Consequently,
`config/settings/production/cache.py` selects Django's `FileBasedCache`
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
(`THROTTLE_CACHE` in `config/settings/base/framework/cache.py`): a
`LocMemCache` with `MAX_ENTRIES` 50,000 and `CULL_FREQUENCY` 3, the same in
development, CI and production, with or without `REDIS_URL`. It holds the
history of the throttles whose **key an anonymous caller mints**, and of the
total page-view cap:

| Throttle | Endpoint | Key |
|----------|----------|-----|
| `PageViewVisitorThrottle`, `PageViewLegacyThrottle` | `POST /analytics/pageview/` | browser `visitor_id`, or one shared legacy bucket |
| `PageViewTotalThrottle` | `POST /analytics/pageview/` | one constant key: at most 3,000 page views a minute in total |
| `PublicAssistantActorThrottle` | `POST /assistant/chat/` | visitor token, member, or one shared legacy bucket |
| `PhoneAuthCodeRequestThrottle` | SMS code requests, only while no SMS daily budget is configured | client address as DRF reads it: in production the `X-Forwarded-For` entry the ALB appended (`NUM_PROXIES`, see [Client IP and proxy trust](backend.md#client-ip-and-proxy-trust)); with `NUM_PROXIES` unset (local, CI) the whole, forgeable header string. A speed bump only. While it applies, enforce mode sends no SMS and observe mode is bounded only per number, so configure `sms_daily_limit` |
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

Route-redirect synchronization uses the ECS task role through boto3's ambient credentials. Scope that role to `amplify:GetApp` and `amplify:UpdateApp` for the environment's specific Amplify app ARN; do not reuse the Secrets Manager-backed SES/SNS credentials for this operation. The backend worker is the only repository-managed writer of the full Amplify custom-rule list; it reconciles the sitemap, API, optional admin/static/media proxies, CMS 301s, and final SPA fallback while preserving unrelated rules. The frontend deploy workflow publishes assets only and must not call `UpdateApp`. Without the app ID, IAM permission, or an enabled background worker, the existing CMS SPA fallback remains available and the admin reports edge synchronization as pending or failed.

The backend deployment defaults `AMPLIFY_BACKEND_PROXY_URL` to
`https://api.i2g.ucmerced.edu` and admin-path proxying to false. Set these values
in the `itg/backend/deploy-config` Secrets Manager object if overriding them.
`AMPLIFY_CONFIG_REVISION` is stamped by the workflow from GitHub's numeric run
ID and attempt; do not define or override it in deployment configuration. If
`BACKGROUND_JOB_METRICS_NAMESPACE` is enabled, also grant the task role
`cloudwatch:PutMetricData`; leaving it empty avoids that permission and does not
affect job processing.

### Production targets

The deploy workflows target the production backend, frontend, and archive.

| GitHub Environment | Purpose |
|--------------------|---------|
| `Manual Deployment Approval` | Single required-reviewer gate shared by every production deployment |
| `AWS ECS - Prod` | Production backend |
| `AWS Amplify - Prod` | Production frontend |
| `AWS ECS - Archive Prod` | Archived event-pages ECS service |

Keep required reviewers on `Manual Deployment Approval`. The three target
environments provide identity boundaries, URLs, and deployment history; settings
live in AWS Secrets Manager. They must not also require reviewers after the unified gate has been
verified; otherwise GitHub requests a second approval.

### Google Sheets

Google service-account credentials live in [`GoogleCredentialConfig`](../../src/apps/core/models/base/service_credentials/google.py) in the database. Paste the service-account JSON into Django admin → Site Settings → Google Credential Configs. No process env vars are required.

### Database-managed credentials

These integrations read credentials from Django admin at runtime (Site Settings, or Mail → Notification Delivery for the email sender and its provider), **not** from process env:

| Model | Purpose |
|-------|---------|
| `AWSCredentialConfig` | Secrets Manager ARN + region + SMS origination number + OTP template |
| `EmailServiceConfig` | Sender identity, campaign rate, and the selected email provider (AWS SES, SMTP, or Microsoft Graph); there is no fallback between providers |
| `SMTPProviderConfig` | SMTP host, port, TLS/SSL, optional username and password |
| `MicrosoftGraphProviderConfig` | Entra tenant ID, client ID, optional sender mailbox, mailbox scope, access-check deny mailbox, InfoSec exception reference |
| `MicrosoftGraphCertificate` | Installed Graph certificates (current, previous for rollback, removed): public data, thumbprints, validity, and the pinned credential-store version of the private key |
| `MicrosoftGraphAccessCheck` | Recorded Graph access checks (probe results, token roles, verdict): the evidence the production go-live gate reads |
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
| Email | Console (stdout) | Console (stdout) | AWS SES / SMTP / Microsoft Graph |
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
