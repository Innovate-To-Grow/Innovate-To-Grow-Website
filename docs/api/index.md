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

JWT configuration (from `src/core/settings/components/integrations/api.py`):
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
| `EmailCodeRequestThrottle` | 10/min | Email code request endpoints |
| `EmailCodeVerifyThrottle` | 20/min | Email code verification endpoints |
| `ContactEmailCreateThrottle` | 5/hour | Contact email creation |
| `PastProjectShareThrottle` | 10/hour | Project sharing |

### Base URL

- Development: `http://localhost:8000` (proxied via Vite at `http://localhost:5173/api/`)
- Production: configured via `VITE_API_BASE_URL` environment variable

## Related sections

- [Architecture: Backend](../architecture/backend.md) — App structure and settings
- [Architecture: Request Flow](../architecture/request-flow.md) — End-to-end request lifecycle
- [Deployment: Environments](../deployment/environments.md) — Environment-specific configuration
