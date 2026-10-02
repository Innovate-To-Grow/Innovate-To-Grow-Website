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

Rate limits are applied per-view, not globally. Active throttle classes:

| Throttle | Rate | Applied to |
|----------|------|------------|
| `LoginRateThrottle` | 10/min | Login endpoint |
| `EmailCodeRequestThrottle` | 30/min | Anonymous email code request endpoints |
| `EmailCodeVerifyThrottle` | 60/min | Code verification and token-confirmation endpoints |
| `PhoneAuthCodeRequestThrottle` | 5/min | Anonymous phone-auth and phone password-reset SMS requests |
| `PhoneCodeRequestThrottle` | 5/min | Authenticated contact-phone/password-change SMS requests |
| `EmailCodeUserRequestThrottle` | 5/min | Authenticated email verification requests |
| `ContactEmailCreateThrottle` | 5/hour | Contact email creation |
| `PastProjectShareRateThrottle` | 10/min | Project sharing |

### Base URL

- Development: `http://localhost:8000` (proxied via Vite at `http://localhost:5173/api/`)
- Production: configured via `VITE_API_BASE_URL` environment variable

## Related sections

- [Architecture: Backend](../architecture/backend.md) — App structure and settings
- [Architecture: Request Flow](../architecture/request-flow.md) — End-to-end request lifecycle
- [Deployment: Environments](../deployment/environments.md) — Environment-specific configuration
