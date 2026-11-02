# API Reference

REST API documentation for the Innovate To Grow platform. The API is built with Django REST Framework and serves the React frontend.

## In this section

- [Routing Overview](routing-overview.md) — URL organization, route groups, and conventions
- [Auth & Mail](auth-and-mail.md) — Authentication, member management, contacts, and email
- [Events](events.md) — Event registration, ticketing, schedule, and check-in
- [Projects](projects.md) — Past project archives and sharing
- [CMS & News](cms-and-news.md) — CMS pages, news articles, analytics, and layout

## Who this is for

Engineers adding or modifying API endpoints, frontend developers consuming the API, and anyone debugging request/response behavior.

## General conventions

### Authentication

Most endpoints require JWT authentication. The frontend sends an `Authorization: Bearer <access_token>` header. Public endpoints use `AllowAny` permission.

DRF authenticates a request *before* it checks permissions, and the SPA's axios client attaches whatever access token local storage holds to every request. On a stock `JWTAuthentication` an expired, garbage, deleted-member or inactive-member token would therefore answer 401 even on an `AllowAny` endpoint (and the client clears the stored session when it cannot refresh). So a public endpoint never runs the strict class:

- It sets `authentication_classes = []` when it never reads the caller (layout, CMS pages/homepage/embed/preview token, news, projects, schedule, assistant config, maintenance bypass).
- It sets `authentication_classes = [SoftJWTAuthentication]` (`apps.authn.security`) when it reads the caller: a valid token identifies the member, and an invalid or expired one is anonymous rather than a 401. Used by draft preview on `/cms/pages/`, `/event/registration-*`, `/analytics/pageview/`, the `GET` of `/projects/past-shares/<id>/` (`can_edit`) and `/assistant/chat/` (the anonymous throttle skips signed-in members).

An endpoint that needs the token for authorization is not `AllowAny` and keeps the strict class, so a bad token there is still a 401 the client can refresh and retry (this includes `PATCH`/`PUT`/`DELETE` on `/projects/past-shares/<id>/`). `apps.authn.tests.security` fails if a public view runs the strict class.

JWT configuration (from `src/config/settings/base/integrations/api/__init__.py`):
- Access token lifetime: 1 hour
- Refresh token lifetime: 7 days
- Rotation: enabled (new refresh token on each refresh)
- Blacklisting: enabled (old refresh tokens invalidated)
- User ID field: `id` (UUID)
- User ID claim: `member_uuid`

### Response format

All endpoints return JSON. List endpoints typically return:

```json
{
  "count": 42,
  "next": "http://…?page=2",
  "previous": null,
  "results": [...]
}
```

Or flat arrays for non-paginated lists.

### Error format

DRF validation errors return field-level messages:

```json
{
  "email": ["This field is required."],
  "password": ["This field may not be blank."]
}
```

Non-field errors use the `non_field_errors` key or `detail` for simple messages.

### Throttling

Two layers limit requests (design and runbook: [Request limits](../integrations/request-limits.md)):

1. **The request limiter** (`RequestRateLimitMiddleware`) limits every request by **scope**, a group of endpoints
   with a priority tier: P0 critical (sign-in, verification codes a person asked for, token refresh, session check,
   check-in, the SES webhook), P1 interactive (`public-read`, `public-write`, `member-read`, `member-write`,
   `member-send`, `staff-admin`, `cli`, `tokenized-link`, `legacy-proxy`), P2 background (`public-background`,
   `telemetry`, `staff-polling`, `checkin-status`, `auth-code-unproven`) and P3 heavy (`public-heavy` for
   `/projects/all/` and `/projects/past-all/`, `ai`, `staff-bulk`, `not-found`). A view names its scope with
   `rate_limit_scope`; unnamed routes fall back by path, method and sign-in. Under overload Smart limit sheds P3,
   then P2, then P1, never P0. Exempt: `/livez/`, `/readyz/`, `/health/`, `/layout/theme.css`, `/robots.txt`,
   one-click unsubscribe and CORS preflights. Seeds: `src/config/settings/base/integrations/request_limits/scopes.py`.
2. **Per-view throttles** (below) are finer limits underneath, set per view with `throttle_classes`, never globally
   (`DEFAULT_THROTTLE_CLASSES` stays unset).

#### The 429 answer

Every refusal by the request limiter has this body, the `Retry-After` header (whole seconds) and
`Cache-Control: no-store`:

```json
{"detail": "Too many requests. Please try again in 12 seconds.", "code": "rate_limited", "retry_after": 12}
```

A per-view throttle answers DRF's `429` (`{"detail": "Request was throttled. Expected available in 12 seconds."}`)
with `Retry-After`; the sign-in lockout answers `code: "login_locked"`. `Retry-After` is listed in
`CORS_EXPOSE_HEADERS`, so the cross-origin SPA can read it. Clients wait it out: the shared Axios client and the auth
client resend an idempotent read once after `Retry-After` (plus jitter; a wait over 10 s fails at once, and a 429 on
`/authn/refresh/` never signs the member out), the admin pollers pause for it (`admin/js/poll-backoff.js`), and the
`i2g-admin` CLI waits and resends reads up to three times. Writes are never resent automatically. Repeated 429s from
one caller in one scope block it for a growing, bounded time, so retrying faster only makes the wait longer.

#### Keys and per-view limits

**Sign-in, emailed-link, verification-code and ALTCHA-challenge endpoints have no per-IP throttle**: campus users share one public IP, so such a limit throttles everyone at once (and is bypassable through `X-Forwarded-For`). They are bounded by the token, the per-destination cooldown/hourly cap and the per-challenge attempt cap instead, and password login by an identifier-keyed failure lockout (`429` with `code: "login_locked"`; see [Auth & Mail](auth-and-mail.md#login)). Per-IP limits for off-campus traffic belong at the edge and exclude campus addresses: see [WAF rate limits](../deployment/waf-rate-limits.md).

Nothing a campus user does is limited by client IP. Every throttle's rate is a **request-limit policy** (Site
Settings → Request Limits, scope `view-…`), read live: an edit applies within seconds, without a restart. Smart
limiting is on by default and takes priority over the manual value: the rate is the default below × the Smart factor of
its parent route scope, never below the scope's floor, and never lowered at all for P0 (sign-in and verification
codes) or fixed scopes; with Smart off the manual value applies. While the request limiter is off
(`REQUEST_RATE_LIMITS_ENABLED=false`, as in the test settings) each throttle uses its default. Seeds:
`src/config/settings/base/integrations/request_limits/view_scopes.py`.

| Throttle | Policy | Default | Keyed on | Applied to |
|----------|--------|---------|----------|------------|
| `PhoneCodeRequestThrottle` | `view-code-send-sms` | 5/min | Member | Authenticated contact-phone, password-change and event-registration SMS requests |
| `EmailCodeUserRequestThrottle` | `view-code-send-email` | 5/min | Member | Authenticated email verification requests |
| `EmailCodeVerifyThrottle` (and the event `SecondaryEmailCodeVerifyThrottle` / `PhoneCodeVerifyThrottle`) | `view-code-verify` | 60/min | Member (one bucket for every signed-in code check) | Change-password and delete-account verify/confirm, contact email/phone verify, event secondary-email and phone verify |
| `ChangePasswordThrottle` | `view-change-password` | 10/hour | Member | `POST /authn/change-password/` |
| `ContactEmailCreateThrottle` | `view-contact-email-create` | 5/hour | Member | Contact email creation |
| `ContactPhoneCreateThrottle` | `view-contact-phone-create` | 5/hour | Member | Contact phone creation |
| `RegistrationCreateThrottle` | `view-registration-create` | 20/hour | Member | `POST /event/registrations/` (emails the ticket) |
| `TicketEmailResendThrottle` | `view-ticket-email-resend` | 10/hour | Member | `POST /event/my-tickets/<id>/resend-email/` |
| `PastProjectShareRateThrottle` / `PastProjectShareUpdateRateThrottle` | `view-past-project-share` / `-update` | 10/min / 120/min | Member | Project sharing |
| `PastProjectAISearchRateThrottle` | `view-ai-search` | 10/min | Member | `POST /projects/past-ai-search/` |
| `CliReadThrottle` / `CliWriteThrottle` | `view-cli-read` / `view-cli-write` | 120/min / 60/min | Member | `/admin-api/` reads / writes (the token exchange has no throttle) |
| `PublicAssistantActorThrottle` | `view-assistant-chat` | 6/min | Visitor token (signed, issued by `GET /assistant/config/`) or member | `POST /assistant/chat/` |
| same, legacy bucket | `view-assistant-legacy` | 60/min | One shared bucket | Chat requests without a valid visitor token (older cached frontend bundles) |
| `PageViewVisitorThrottle` | `view-pageview-visitor` | 120/min | Browser `visitor_id` (random, client-chosen) | `POST /analytics/pageview/` |
| `PageViewLegacyThrottle` | `view-pageview-legacy` | 600/min | One shared bucket | Page views without a usable `visitor_id` |
| `PageViewTotalThrottle` | `view-pageview-total` | 3,000/min | One constant key (all page views) | `POST /analytics/pageview/`; the only one of these that can drop an honest page view, and only during a flood |
| `PhoneAuthCodeRequestThrottle` | `view-code-send-sms-ip` | 5/min | Client IP | Fallback only: anonymous phone-auth and phone password-reset SMS requests, attached by `sms_request_throttles()` only while no SMS daily budget (`sms_daily_limit`) is configured |
| `SesEventThrottle` | `view-ses-events` (fixed) | 600/min | Client IP | `POST /mail/ses/events/`, counted only after the SNS signature verifies (callers are AWS SNS, never users) |
| `SesRejectedThrottle` | `view-ses-rejected` (fixed) | 60/min | Client IP | Calls to the SES webhook whose envelope or signature is rejected, counted apart so junk never uses up the signed deliveries' allowance |

Limits that are not throttle classes:

| Limit | Keyed on | Where |
|-------|----------|-------|
| Verification sends: 60-second cooldown, hourly cap | Destination (email address or phone number) | [Send verification](../deployment/send-verification.md) |
| Code-guess attempts and degradation | Challenge and destination | [Auth & Mail](auth-and-mail.md#rate-limit-policy-no-client-ip-limits-on-sign-in) |
| Password sign-in lockout (member and admin-panel login) | Account identifier; the admin "remembered" form uses a separate counter only the signed-cookie holder can reach | [Auth & Mail](auth-and-mail.md#login) |
| SMS daily budget (`sms_daily_limit`) | Global, set in Django admin | [Send verification](../deployment/send-verification.md#sms-daily-budget) |
| Assistant and AI search token budgets | Visitor token or member, plus one global budget per feature (limit set in Django admin) | [Assistant and AI search limits](../integrations/assistant-limits.md) |
| Maintenance bypass: 20 wrong passwords per 15 minutes (policy `view-maintenance-bypass`), then every attempt `429` until the period ends | Everyone together (one shared password; never the client IP) | `POST /maintenance/bypass/` |
| Staff invitation: 10 submissions per hour (policy `view-invitation`) | The invitation | `POST /authn/invite/<token>/` |
| CSP reports: 60 per minute (policy `view-csp-report`, seeded from `CSP_REPORT_RATE_LIMIT` / `CSP_REPORT_RATE_WINDOW_SECONDS`) | Client address | `POST /csp-report/` (over the limit a report is dropped, still `204`) |

Throttle histories live in the Django cache. The per-member throttles use the default cache, which in production is per container ([Environments](../deployment/environments.md#production-cache-today)). The assistant, page-view, SMS fallback and SES webhook throttles use the bounded in-process `throttle` alias, so their rates are per Uvicorn worker process ([The `throttle` cache alias](../deployment/environments.md#the-throttle-cache-alias)). The limits in the second table are counted in PostgreSQL.

### Base URL

- Development: `http://localhost:8000` (proxied via Vite at `http://localhost:5173/api/`)
- Production: configured via `VITE_API_BASE_URL` environment variable

## Related sections

- [Architecture: Backend](../architecture/backend.md) — App structure and settings
- [Architecture: Request Flow](../architecture/request-flow.md) — End-to-end request lifecycle
- [Deployment: Environments](../deployment/environments.md) — Environment-specific configuration
