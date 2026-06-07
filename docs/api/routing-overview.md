# Routing Overview

URL organization for the Django backend, defined in `src/apps/core/urls.py` with delegation to app-level routers.

## Root URL patterns

| Path | Handler | Description |
|------|---------|-------------|
| `/` | `root_index` | Static landing response |
| `/robots.txt` | `robots_txt` | Search engine directives |
| `/admin/login/` | `AdminLoginView` | Custom admin login (overrides default) |
| `/admin/` | Django admin | Unfold-themed admin interface |
| `/livez/` | `HealthCheckMiddleware` | Liveness probe without DB access (intercepted before URL routing) |
| `/readyz/` | `HealthCheckMiddleware` | Readiness probe with DB access (intercepted before URL routing) |
| `/health/` | `HealthCheckMiddleware` | Frontend-compatible health and maintenance status |
| `/maintenance/bypass/` | `MaintenanceBypassView` | Maintenance mode bypass with password |
| `/layout/` | `LayoutAPIView` | Combined menu + footer data for frontend |
| `/authn/` | `apps.authn.urls` | Authentication and member endpoints |
| `/cms/` | `apps.cms.cms_urls` | CMS page endpoints |
| `/news/` | `apps.cms.news_urls` | News article endpoints |
| `/analytics/` | `apps.cms.analytics_urls` | Page view tracking |
| `/event/` | `apps.event.urls` | Event registration and management |
| `/projects/` | `apps.projects.urls` | Past project archives |
| `/mail/` | `apps.mail.urls` | Magic login links |
| `/admin-api/` | `apps.cli_admin.urls` | OAuth2 + PKCE generic CRUD for the `i2g-admin` CLI |
| `/ckeditor5/` | CKEditor 5 | Rich text editor file uploads |

## Route groups by domain

### Authentication (`/authn/`)

30+ endpoints. See [Auth & Mail](auth-and-mail.md) for details.

Key groups:
- Registration and login (`/authn/register/`, `/authn/login/`)
- Email auth challenges (`/authn/email-auth/request-code/`, `/authn/email-auth/verify-code/`)
- Password management (`/authn/password-reset/`, `/authn/change-password/`)
- Profile (`/authn/profile/`)
- Contact emails and phones (`/authn/contact-emails/`, `/authn/contact-phones/`)
- Token refresh (`/authn/refresh/`)
- Auto-login (`/authn/unsubscribe-login/`)
- Admin (`/authn/admin-invite/`)

### Content (`/cms/`, `/news/`, `/analytics/`, `/layout/`)

See [CMS & News](cms-and-news.md) for details.

- `/cms/pages/{route}/` — Dynamic page content by route path
- `/cms/live-preview/{page_id}/` — Admin live preview
- `/news/` — Article list (paginated)
- `/news/{id}/` — Article detail
- `/analytics/pageview/` — Track page views
- `/layout/` — Menu and footer data

### Events (`/event/`)

11 endpoints. See [Events](events.md) for details.

- Registration options and creation
- Ticket management and auto-login
- Schedule data
- Check-in scanning
- Phone verification

### Projects (`/projects/`)

6 endpoints. See [Projects](projects.md) for details.

- Past project listing (paginated and full)
- Project detail
- Sharing

### Mail (`/mail/`)

- `/mail/login-link/` — Token-based auto-login from campaign and ticket emails (legacy alias: `/mail/magic-login/`)

### Admin API (`/admin-api/`)

Generic, denylist-gated CRUD for the `i2g-admin` terminal CLI, authenticated by a short-lived bearer token minted from the staff admin login via OAuth2 + PKCE. Staff status is the gate (no per-model permissions); a SimpleJWT is rejected here. See [CMS & Admin: i2g-admin CLI](../cms-admin/cli-admin.md) for the full guide.

- `/admin-api/oauth/authorize/`, `/admin-api/oauth/token/` — PKCE authorization-code flow
- `/admin-api/whoami/`, `/admin-api/models/`, `/admin-api/models/{app}/{model}/schema/`
- `/admin-api/records/{app}/{model}/` — list / create
- `/admin-api/records/{app}/{model}/{pk}/` — retrieve / update / delete

## Frontend route mapping

The frontend router (`pages/src/app/router.tsx`) maps browser URLs to React components. Most frontend routes call one or more API endpoints:

| Frontend route | Primary API call |
|---------------|-----------------|
| `/` | `/layout/` + CMS page fetch (homepage route from SiteSettings) |
| `/login` | `/authn/login/`, `/authn/public-key/` |
| `/register` | `/authn/register/`, `/authn/public-key/` |
| `/news` | `/news/` |
| `/news/:id` | `/news/{id}/` |
| `/past-projects` | `/projects/past/` |
| `/projects/:id` | `/projects/{id}/` |
| `/event-registration` | `/event/registration-options/`, `/event/registrations/` |
| `/schedule` | `/event/schedule/` |
| `/account` | `/authn/profile/`, `/authn/contact-emails/`, `/authn/contact-phones/` |
| `*` (catch-all) | `/cms/pages/{path}/` |

## Extension points

When adding a new API endpoint:

1. Create views and serializers in the appropriate app
2. Add URL patterns in the app's `urls.py`
3. If it's a new top-level path, register it in `src/apps/core/urls.py`
4. Apply appropriate permission classes and throttles per-view
5. Update the frontend feature API module if the frontend will consume it

## Related pages

- [Architecture: Backend](../architecture/backend.md) — App structure
- [Architecture: Request Flow](../architecture/request-flow.md) — Request lifecycle
- [Auth & Mail](auth-and-mail.md) — Auth endpoint details
