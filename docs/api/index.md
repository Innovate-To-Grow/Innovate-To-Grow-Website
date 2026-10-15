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

JWT configuration (from `src/config/settings/components/integrations/api.py`):
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

Rate limits are applied per-view, not globally. **Sign-in, emailed-link, verification-code and ALTCHA-challenge endpoints have no per-IP throttle**: campus users share one public IP, so such a limit throttles everyone at once (and is bypassable through `X-Forwarded-For`). They are bounded by the token, the per-destination cooldown/hourly cap and the per-challenge attempt cap instead, and password login by an identifier-keyed failure lockout (`429` with `code: "login_locked"`; see [Auth & Mail](auth-and-mail.md#login)). Per-IP limits for off-campus traffic belong at the edge and exclude campus addresses: see [WAF rate limits](../deployment/waf-rate-limits.md).

Nothing a campus user does is limited by client IP. Active throttle classes, by what they are keyed on:

| Throttle | Rate | Keyed on | Applied to |
|----------|------|----------|------------|
| `PhoneCodeRequestThrottle` | 5/min | Member | Authenticated contact-phone, password-change and event-registration SMS requests |
| `EmailCodeUserRequestThrottle` | 5/min | Member | Authenticated email verification requests |
| `SecondaryEmailCodeVerifyThrottle` | 60/min | Member | Event-registration secondary-email verification |
| `ContactEmailCreateThrottle` | 5/hour | Member | Contact email creation |
| `PastProjectShareRateThrottle` | 10/min | Member | Project sharing |
| `PastProjectAISearchRateThrottle` | 10/min | Member | `POST /projects/past-ai-search/` |
| `CliReadThrottle` / `CliWriteThrottle` | 120/min / 60/min | Member | `/admin-api/` reads / writes (the token exchange has no throttle) |
| `PublicAssistantActorThrottle` | 6/min | Visitor token (signed, issued by `GET /assistant/config/`) or member | `POST /assistant/chat/` |
| same, legacy bucket | 60/min | One shared bucket | Chat requests without a valid visitor token (older cached frontend bundles) |
| `PageViewVisitorThrottle` | 120/min | Browser `visitor_id` (random, client-chosen) | `POST /analytics/pageview/` |
| `PageViewLegacyThrottle` | 600/min | One shared bucket | Page views without a usable `visitor_id` |
| `PageViewTotalThrottle` | 3,000/min | One constant key (all page views) | `POST /analytics/pageview/`; the only one of these that can drop an honest page view, and only during a flood |
| `EmailCodeVerifyThrottle` | 60/min | Client IP, anonymous requests only | Attached to authenticated verify views, where it never applies |
| `PhoneAuthCodeRequestThrottle` | 5/min | Client IP | Fallback only: anonymous phone-auth and phone password-reset SMS requests, attached by `sms_request_throttles()` only while no SMS daily budget (`sms_daily_limit`) is configured |
| `SesEventThrottle` | 600/min | Client IP | `POST /mail/ses/events/` (callers are AWS SNS, never users) |

Limits that are not throttle classes:

| Limit | Keyed on | Where |
|-------|----------|-------|
| Verification sends: 60-second cooldown, hourly cap | Destination (email address or phone number) | [Send verification](../deployment/send-verification.md) |
| Code-guess attempts and degradation | Challenge and destination | [Auth & Mail](auth-and-mail.md#rate-limit-policy-no-client-ip-limits-on-sign-in) |
| Password sign-in lockout (member and admin-panel login) | Account identifier; the admin "remembered" form uses a separate counter only the signed-cookie holder can reach | [Auth & Mail](auth-and-mail.md#login) |
| SMS daily budget (`sms_daily_limit`) | Global, set in Django admin | [Send verification](../deployment/send-verification.md#sms-daily-budget) |
| Assistant and AI search token budgets | Visitor token or member, plus one global budget per feature (limit set in Django admin) | [Assistant and AI search limits](../integrations/assistant-limits.md) |

Throttle histories live in the Django cache. The per-member throttles use the default cache, which in production is per container ([Environments](../deployment/environments.md#production-cache-today)). The assistant, page-view, SMS fallback and SES webhook throttles use the bounded in-process `throttle` alias, so their rates are per Uvicorn worker process ([The `throttle` cache alias](../deployment/environments.md#the-throttle-cache-alias)). The limits in the second table are counted in PostgreSQL.

### Base URL

- Development: `http://localhost:8000` (proxied via Vite at `http://localhost:5173/api/`)
- Production: configured via `VITE_API_BASE_URL` environment variable

## Related sections

- [Architecture: Backend](../architecture/backend.md) — App structure and settings
- [Architecture: Request Flow](../architecture/request-flow.md) — End-to-end request lifecycle
- [Deployment: Environments](../deployment/environments.md) — Environment-specific configuration
