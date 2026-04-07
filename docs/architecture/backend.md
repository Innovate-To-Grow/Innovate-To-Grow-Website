# Backend Architecture

The backend is a Django 5.2 application with Django REST Framework, rooted at `src/`. It serves a REST API consumed by the React frontend and provides a customized Django admin interface.

## Django apps

| App | Purpose | Key models |
|-----|---------|------------|
| `core` | Base models, middleware, settings, management commands, shared utilities | `ProjectControlModel`, `SiteMaintenanceControl`, `EmailServiceConfig`, `SMSServiceConfig`, `GoogleCredentialConfig` |
| `authn` | Authentication, member management, contacts, admin invitations | `Member`, `ContactEmail`, `ContactPhone`, `EmailAuthChallenge`, `RSAKeypair`, `AdminInvitation` |
| `cms` | CMS pages and blocks, news, analytics, menus, footer, site settings | `CMSPage`, `CMSBlock`, `CMSAsset`, `NewsArticle`, `NewsFeedSource`, `PageView`, `Menu`, `FooterContent`, `SiteSettings` |
| `event` | Event registration, ticketing, schedule, check-in | `Event`, `EventRegistration`, `Ticket`, `Question`, `CheckIn`, `CheckInRecord`, `CurrentProjectSchedule`, `EventScheduleSection`, `EventScheduleTrack`, `EventScheduleSlot` |
| `projects` | Past project archives and sharing | `Semester`, `Project`, `PastProjectShare` |
| `mail` | Email campaigns and delivery | `EmailCampaign`, `RecipientLog`, `MagicLoginToken` |
| `sponsors` | Sponsor management | Sponsor models |

## Base model: ProjectControlModel

Defined in `src/core/models/base.py`. Nearly all domain models inherit from this abstract class.

```
ProjectControlModel (abstract)
├── id            — UUIDField, primary key (uuid4)
├── created_at    — DateTimeField (auto_now_add)
├── updated_at    — DateTimeField (auto_now)
└── objects       — ProjectControlManager
```

**Manager behavior:** The default `objects` manager uses `ProjectControlQuerySet`. Some models layer additional filtering (e.g., soft-delete exclusion).

### Model mixins

Additional abstract mixins in `src/core/models/mixins/`:

| Mixin | Fields |
|-------|--------|
| `AuthoredModel` | `created_by`, `updated_by` (FK to Member, SET_NULL) |
| `OrderedModel` | `order` (PositiveIntegerField, indexed) |
| `ActiveModel` | `is_active` (BooleanField, indexed) |

## Settings structure

Settings live in `src/core/settings/` with a modular import pattern:

```
core/settings/
├── base.py                          # Wildcard imports from components/
├── dev.py                           # DEBUG=True, SQLite, console email
├── ci.py                            # PostgreSQL container, test credentials
├── prod.py                          # PostgreSQL+SSL, S3, Redis, SMTP
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

**Import order matters:** `environment` → `django` → `admin` → `api` → `editor` → `production`. Each file may reference variables defined in earlier imports.

### Environment differences

| Concern | Dev | CI | Prod |
|---------|-----|-----|------|
| Database | SQLite | PostgreSQL (GH Actions service) | PostgreSQL + SSL |
| Cache | LocMemCache | LocMemCache | Redis (file fallback) |
| Email | Console backend | Console backend | AWS SES / SMTP |
| File storage | Local filesystem | Local filesystem | S3 via django-storages |
| Passwords | Plain text OK | Plain text OK | Argon2/bcrypt required |
| Debug | True | False | False |

## Auth system

Detailed in [API: Auth & Mail](../api/auth-and-mail.md). Summary:

- **Member model** (`src/authn/models/member.py`): extends `AbstractUser` + `ProjectControlModel`. PK is a UUID. `USERNAME_FIELD = "id"`.
- **JWT**: SimpleJWT with 1-hour access tokens, 7-day refresh tokens, rotation, and blacklisting.
- **Email challenges**: `EmailAuthChallenge` model provides time-limited codes for registration, login, password reset, account deletion, and contact verification.
- **RSA encryption**: Client encrypts passwords with a server-provided RSA public key before transmission. Keys rotate on each login.
- **Throttling**: Per-view throttle classes. Never set `DEFAULT_THROTTLE_CLASSES` globally — it breaks the test suite because tests run from `127.0.0.1`.

## Middleware stack

Defined in `src/core/settings/components/framework/django.py`:

1. `GZipMiddleware` — Response compression
2. `CorsMiddleware` — Cross-origin headers (django-cors-headers)
3. `HealthCheckMiddleware` — Intercepts `/health/` before all other processing
4. `SecurityMiddleware` — HSTS, SSL redirect (prod only)
5. `SessionMiddleware` — Session handling
6. `CommonMiddleware` — URL normalization
7. `CsrfViewMiddleware` — CSRF protection
8. `AuthenticationMiddleware` — User attachment to request
9. `MessageMiddleware` — Flash messages
10. `XFrameOptionsMiddleware` — Clickjacking protection

### HealthCheckMiddleware

`src/core/middleware.py` — intercepts `GET /health/` and returns JSON:

```json
{"status": "ok", "database": true, "maintenance": false}
```

Always returns HTTP 200 (for ALB health probes). The `database` and `maintenance` fields reflect actual state.

## Singleton configuration models

Several models in `src/core/models/` use a singleton pattern (only one active record):

| Model | Purpose | Location |
|-------|---------|----------|
| `SiteMaintenanceControl` | Maintenance mode toggle with bypass password | `core/models/web.py` |
| `EmailServiceConfig` | AWS SES or SMTP credentials | `core/models/service_credentials.py` |
| `SMSServiceConfig` | Twilio Verify API credentials | `core/models/service_credentials.py` |
| `GoogleCredentialConfig` | Google service account JSON | `core/models/service_credentials.py` |

Each provides a `load()` class method that returns the active configuration.

## Management commands

| Command | Location | Purpose |
|---------|----------|---------|
| `resetdb` | `core/management/commands/resetdb.py` | Dev-only: drops DB, regenerates migrations, seeds admin user |
| `seed_service_configs` | `core/management/commands/seed_service_configs.py` | Creates default EmailServiceConfig and SMSServiceConfig from `.env` |
| `createsuperuser` | `authn/management/commands/createsuperuser.py` | Custom: prompts for email, not username |
| `sync_news` | `cms/management/commands/sync_news.py` | Fetches and parses RSS feeds into NewsArticle records |

## Related pages

- [Frontend](frontend.md) — How the React app consumes this backend
- [Request Flow](request-flow.md) — End-to-end request lifecycle
- [API Reference](../api/index.md) — Endpoint documentation
- [Deployment: Backend](../deployment/backend.md) — Container and ECS configuration
