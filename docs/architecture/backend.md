# Backend Architecture

The backend is a Django 5.2 application with Django REST Framework, rooted at `src/`. It serves a REST API consumed by the React frontend and provides a customized Django admin interface.

## Django apps

| App | Purpose | Key models |
|-----|---------|------------|
| `core` | Base models, middleware, settings, management commands, shared utilities | `ProjectControlModel`, `SiteMaintenanceControl`, `EmailServiceConfig`, `GoogleCredentialConfig`, `AWSCredentialConfig`, `BackgroundJob`, `DeliveryRateLimit` |
| `authn` | Authentication, member management, contacts, admin invitations | `Member`, `ContactEmail`, `ContactPhone`, `EmailAuthChallenge`, `PhoneVerificationChallenge`, `RSAKeypair`, `AdminInvitation` |
| `cms` | CMS pages and blocks, news, analytics, menus, footer, site settings | `CMSPage`, `CMSBlock`, `CMSAsset`, `NewsArticle`, `NewsFeedSource`, `PageView`, `Menu`, `FooterContent`, `SiteSettings` |
| `event` | Event registration, ticketing, schedule, check-in | `Event`, `EventRegistration`, `Ticket`, `Question`, `CheckIn`, `CheckInRecord`, `CurrentProjectSchedule`, `EventScheduleSection`, `EventScheduleTrack`, `EventScheduleSlot` |
| `projects` | Past project archives and sharing | `Semester`, `Project`, `PastProjectShare` |
| `mail` | Email campaigns and delivery | `EmailCampaign`, `RecipientLog`, `LoginLinkToken` |
| `sponsors` | Sponsor management | Sponsor models |

## Base model: ProjectControlModel

Defined in `src/apps/core/models/base/control.py`. Nearly all domain models inherit from this abstract class.

```
ProjectControlModel (abstract)
├── id            — UUIDField, primary key (uuid4)
├── created_at    — DateTimeField (auto_now_add)
├── updated_at    — DateTimeField (auto_now)
└── objects       — ProjectControlManager
```

**Manager behavior:** The default `objects` manager uses `ProjectControlQuerySet`. Some models layer additional filtering (e.g., soft-delete exclusion).

### Model mixins

Additional abstract mixins in `src/apps/core/models/mixins/`:

| Mixin | Fields |
|-------|--------|
| `AuthoredModel` | `created_by`, `updated_by` (FK to Member, SET_NULL) |
| `OrderedModel` | `order` (PositiveIntegerField, indexed) |
| `ActiveModel` | `is_active` (BooleanField, indexed) |

## Settings structure

Settings live in `src/config/settings/` with a modular import pattern:

```
config/settings/
├── base.py                          # Wildcard imports from components/
├── local.py                         # DEBUG=True, SQLite, console email
├── test.py                          # PostgreSQL container, test credentials
├── production.py                    # Loads production component overrides
└── components/
    ├── framework/
    │   ├── environment.py           # BASE_DIR, .env loading, AWS SES, timezone
    │   └── django.py               # INSTALLED_APPS, MIDDLEWARE, templates, auth
    ├── integrations/
    │   ├── api.py                   # DRF config, JWT (1h access, 7d refresh)
    │   ├── admin.py                 # Unfold theme, sidebar, tab groups
    │   └── editor.py               # CKEditor 5 toolbar and uploads
    └── production.py                # S3 storage, CORS, logging, Redis cache
```

**Import order matters:** `base.py` installs the legacy import shim, then imports `environment` → `django` → `admin` → `api` → `editor`. `production.py` loads `base` before applying `components/production.py`. Later files may reference variables defined by earlier imports.

### Environment differences

| Concern | Local | Test/CI | Production |
|---------|-----|-----|------|
| Database | SQLite | PostgreSQL (GH Actions service) | PostgreSQL + SSL |
| Cache | LocMemCache | LocMemCache | Redis; required when the public assistant is enabled |
| Email | Console backend | Console backend | Application services use AWS SES |
| File storage | Local filesystem | Local filesystem | S3 via django-storages |
| Password transport | Plain text accepted | Plain text accepted | RSA encryption required |
| Debug | True | False | False |

## Auth system

Detailed in [API: Auth & Mail](../api/auth-and-mail.md). Summary:

- **Member model** (`src/apps/authn/models/members/member.py`): extends `AbstractUser` + `ProjectControlModel`. PK is a UUID. `USERNAME_FIELD = "id"`.
- **JWT**: SimpleJWT with 1-hour access tokens, 7-day refresh tokens, rotation, and blacklisting.
- **Session bootstrap**: `GET /authn/session/` requires JWT authentication and returns the current serialized member, the server-calculated profile-completion flag, and the next step. The frontend treats this response—not its persisted profile snapshot—as authoritative.
- **Email challenges**: `EmailAuthChallenge` provides time-limited codes for registration, login, password reset, account deletion, and contact verification. Attempt counts, expiry, verification, and token consumption use row locks or conditional status updates so errors do not roll state back and successful credentials are one-time.
- **SMS challenges**: `PhoneVerificationChallenge` stores a hashed OTP, purpose, attempt budget, expiry, and consumption state in the database. Request endpoints return its UUID as `challenge_id`; verification by phone number without that ID is a temporary compatibility path.
- **RSA encryption**: Clients encrypt password fields with the public key from `/authn/public-key/`. The active `auth-encryption` key rotates after one day into a new row. Retired keys remain decryptable for 24 hours and are retained, then purged, at 48 hours. An unknown or expired `key_id` fails closed rather than falling back to the current private key.
- **Impersonation**: Admin-issued impersonation links are short-lived and atomically consumed before JWTs are returned, so only one concurrent exchange can succeed.
- **Throttling**: Per-view throttle classes. Never set `DEFAULT_THROTTLE_CLASSES` globally — it breaks the test suite because tests run from `127.0.0.1`.

## Middleware stack

Defined in `src/config/settings/components/framework/django.py`:

1. `GZipMiddleware` — Response compression
2. `CorsMiddleware` — Cross-origin headers (django-cors-headers)
3. `HealthCheckMiddleware` — Intercepts `/livez/`, `/readyz/`, and `/health/` before all other processing
4. `SecurityMiddleware` — HSTS, SSL redirect (prod only)
5. `ContentSecurityPolicyMiddleware` — request nonce plus report-only/enforcing CSP
6. `SessionMiddleware` — Session handling
7. `CommonMiddleware` — URL normalization
8. `CsrfViewMiddleware` — CSRF protection
9. `AuthenticationMiddleware` — User attachment to request
10. `MessageMiddleware` — Flash messages
11. `XFrameOptionsMiddleware` — Clickjacking protection

### HealthCheckMiddleware

`src/apps/core/middleware/__init__.py` provides three health endpoints:

| Path | Purpose | Database check |
|------|---------|----------------|
| `/livez/` | Container and ALB liveness | No |
| `/readyz/` | Deployment and monitoring readiness | Yes |
| `/health/` | Frontend-compatible health and maintenance status | Yes |

`/readyz/` and `/health/` return HTTP 503 when database connectivity fails. `/livez/` avoids DB access so database saturation does not trigger ECS task replacement loops.

## Active configuration models

The following configuration selectors enforce their single-active invariant in both model code and a partial database unique constraint:

| Model | Scope | Empty-state result |
|-------|-------|--------------------|
| `AWSCredentialConfig` | One active globally | Unsaved defaults; AWS-backed operations remain unconfigured |
| `EmailServiceConfig` | One active globally | Unsaved sender defaults; no inactive row is reused |
| `GoogleCredentialConfig` | One active globally | Unsaved defaults; Sheets operations remain unconfigured |
| `GmailAccessAccount` | One active globally | Unsaved defaults; Gmail import remains unconfigured |
| `SystemIntelligenceConfig` | One active globally | Unsaved defaults |
| `CurrentProjectSchedule` | One active globally | `None` |
| `PastProjectsSheetConfig` | One active globally | `None` |
| `MemberSheetSyncConfig` | One enabled globally | Unsaved disabled defaults |
| `RSAKeypair` | One active per `name` | The auth service creates a new `auth-encryption` row |

`load()` reads only an explicitly active or enabled row. It never revives or silently uses the most recently updated inactive row. If corruption somehow produces multiple active rows, `.get()` raises instead of selecting one arbitrarily. See [CMS/Admin Operations](../cms-admin/operations.md#active-configuration-recovery) for verification and recovery.

## Management commands

| Command | Location | Purpose |
|---------|----------|---------|
| `resetdb` | `core/management/commands/resetdb.py` | Dev-only: drops DB, regenerates migrations, seeds admin user |
| `seed_service_configs` | `core/management/commands/seed_service_configs.py` | Creates skeleton EmailServiceConfig row and optional AWSCredentialConfig from local env |
| `verify_service_configs` | `core/management/commands/verify_service_configs.py` | Verifies active service configs exist before removing env vars |
| `migrate_locked` | `authn/management/commands/migrate_locked.py` | Runs migrations on PostgreSQL while holding the repository advisory lock |
| `run_background_worker` | `core/management/commands/run_background_worker.py` | Claims and processes durable background jobs; `--once` processes one batch |
| `createsuperuser` | `authn/management/commands/createsuperuser.py` | Custom: prompts for email, not username |
| `sync_news` | `cms/management/commands/sync_news.py` | Fetches and parses RSS feeds into NewsArticle records |

## Related pages

- [Frontend](frontend.md) — How the React app consumes this backend
- [Request Flow](request-flow.md) — End-to-end request lifecycle
- [API Reference](../api/index.md) — Endpoint documentation
- [Deployment: Backend](../deployment/backend.md) — Container and ECS configuration
