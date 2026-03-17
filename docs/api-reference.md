# API Reference

All endpoints are served by the Django backend. In local development, the Vite dev server proxies `/api/*` requests to `http://localhost:8000` (stripping the `/api` prefix). In production, the frontend calls the backend API domain directly via `VITE_API_BASE_URL`.

## Common Patterns

- **UUID primary keys** — All resource IDs are UUIDs (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- **Authentication** — Bearer token in `Authorization` header: `Authorization: Bearer <access_token>`
- **Default permission** — `IsAuthenticated`. Public endpoints explicitly allow anonymous access.
- **Error responses** — DRF standard format: `{"field_name": ["Error message"]}` or `{"detail": "Error message"}`
- **Pagination** — Page-number pagination where noted: `?page=1&page_size=10`. Response: `{"count", "next", "previous", "results"}`

---

## Authentication (`/authn/`)

### Public Endpoints

These endpoints do not require authentication.

| Method | Path | Purpose | Throttle |
|--------|------|---------|----------|
| GET | `/authn/public-key/` | Get RSA public key for password encryption | — |
| POST | `/authn/register/` | Register a new user | EmailCodeRequest (10/min) |
| POST | `/authn/register/verify-code/` | Verify registration email code | EmailCodeVerify (20/min) |
| POST | `/authn/register/resend-code/` | Resend registration code | EmailCodeRequest (10/min) |
| POST | `/authn/login/` | Login with email + password | Login (10/min) |
| POST | `/authn/login/request-code/` | Request login verification code | EmailCodeRequest (10/min) |
| POST | `/authn/login/verify-code/` | Verify login code | EmailCodeVerify (20/min) |
| POST | `/authn/email-auth/request-code/` | Request unified email auth code | EmailCodeRequest (10/min) |
| POST | `/authn/email-auth/verify-code/` | Verify unified email auth code | EmailCodeVerify (20/min) |
| POST | `/authn/refresh/` | Refresh JWT access token | — |
| POST | `/authn/password-reset/request-code/` | Request password reset code | EmailCodeRequest (10/min) |
| POST | `/authn/password-reset/verify-code/` | Verify password reset code | EmailCodeVerify (20/min) |
| POST | `/authn/password-reset/confirm/` | Set new password after reset | EmailCodeVerify (20/min) |

### Authenticated Endpoints

These require a valid JWT access token.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/authn/profile/` | Get current user profile |
| PATCH | `/authn/profile/` | Update profile fields or upload profile image |
| GET | `/authn/account-emails/` | Get user's account email addresses |
| POST | `/authn/change-password/` | Change password (direct, with current password) |
| POST | `/authn/change-password/request-code/` | Request password change verification code |
| POST | `/authn/change-password/verify-code/` | Verify password change code |
| POST | `/authn/change-password/confirm/` | Confirm password change with code |
| GET | `/authn/contact-emails/` | List contact emails |
| POST | `/authn/contact-emails/` | Add a contact email |
| PATCH | `/authn/contact-emails/<uuid>/` | Update a contact email |
| DELETE | `/authn/contact-emails/<uuid>/` | Remove a contact email |
| POST | `/authn/contact-emails/<uuid>/request-verification/` | Request email verification code |
| POST | `/authn/contact-emails/<uuid>/verify-code/` | Verify contact email code |
| GET | `/authn/contact-phones/` | List contact phones |
| POST | `/authn/contact-phones/` | Add a contact phone |
| PATCH | `/authn/contact-phones/<uuid>/` | Update a contact phone |
| DELETE | `/authn/contact-phones/<uuid>/` | Remove a contact phone |

### Authentication Flows

**Registration:**
1. `POST /authn/register/` with `{email, password, first_name, last_name, organization}` — password is RSA-encrypted client-side
2. Returns `202 Accepted` with `{challenge_token, next_step: "verify_code"}`
3. `POST /authn/register/verify-code/` with `{challenge_token, code}` — returns JWT tokens + member data

**Login:**
1. `POST /authn/login/` with `{email, password}` — password is RSA-encrypted client-side
2. Returns `{access, refresh, member: {...}, next_step: "account"}`

**Password Reset:**
1. `POST /authn/password-reset/request-code/` with `{email}` — sends code via email
2. `POST /authn/password-reset/verify-code/` with `{challenge_token, code}` — returns verification token
3. `POST /authn/password-reset/confirm/` with `{verification_token, new_password}` — returns JWT tokens

**Token Refresh:**
- `POST /authn/refresh/` with `{refresh}` — returns `{access, refresh}` (old refresh token is blacklisted)

### Password Encryption

All password fields must be RSA-encrypted before submission:
1. Fetch the public key from `GET /authn/public-key/`
2. Encrypt the password using RSA-OAEP with the public key
3. Base64-encode the ciphertext
4. Send the base64 string as the password value

In development (`REQUIRE_ENCRYPTED_PASSWORDS = False`), plaintext passwords are also accepted.

---

## Layout (`/layout/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/layout/` | AllowAny | Get site layout data |

**Response:**
```
{
  "menus": [{"name", "display_name", "items": [...]}],
  "footer": {"name", "content": {...}},
  "homepage_route": "/home-during-event",
  "sheets_data": {
    "current-event": {...}
  }
}
```

The response is cached for 600 seconds. Cache is invalidated when Menu, FooterContent, SiteSettings, or CMSPage records that affect the selected homepage are updated.

`homepage_route` is derived from the selected homepage CMS page in Site Settings. If no page is selected or the selected page is unavailable, the published `/` page is used as the fallback homepage.

When an active `current-event` sheet source exists, the response includes `sheets_data.current-event` so CMS-driven homepages can render schedule and project blocks without an extra sequential fetch.

---

## CMS Pages (`/cms/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/cms/pages/` | AllowAny | Get the root CMS page (route="/") |
| GET | `/cms/pages/<route>/` | AllowAny | Get a CMS page by its route path |
| GET | `/cms/preview/<token>/` | AllowAny | Fetch a preview by temporary token |

**Response (page):**
```
{
  "slug": "about",
  "route": "/about",
  "title": "About Us",
  "page_css_class": "about-page",
  "meta_description": "...",
  "blocks": [
    {"block_type": "hero", "sort_order": 0, "data": {...}},
    {"block_type": "rich_text", "sort_order": 1, "data": {"body_html": "..."}}
  ]
}
```

- Only pages with `status="published"` are returned (404 otherwise)
- Staff users can append `?preview=true` to see draft/archived pages
- Published pages are cached for 300 seconds
- Preview tokens are generated by the admin and cached for 600 seconds

---

## Google Sheets (`/sheets/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/sheets/<slug>/` | AllowAny | Get parsed Google Sheets data by source slug |
| POST | `/sheets/<slug>/refresh/` | IsAdminUser | Force-refresh cached sheet data |

**Response:**
```
{
  "slug": "current-event",
  "title": "Spring 2025 Event",
  "sheet_type": "current-event",
  "rows": [
    {"Track": "1", "Order": "1", "Year-Semester": "2025-1 Spring", ...}
  ],
  "track_infos": [
    {"name": "Track 1", "room": "COB2 130", "zoomLink": "..."}
  ]
}
```

- Uses stale-while-revalidate caching: fresh data is returned from cache; stale data triggers a background refresh
- Cache TTL is configurable per source (default 300 seconds)
- Returns 502 if Google Sheets API is unavailable or misconfigured

---

## News (`/news/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/news/` | AllowAny | List news articles (paginated) |
| GET | `/news/<uuid>/` | AllowAny | Get a single news article |

**List response fields:** id, title, source_url, summary, image_url, published_at

**Detail response adds:** author, content, hero_image_url, hero_caption

Pagination: `?page=1&page_size=10` (default page size configured in `NewsPageNumberPagination`)

Articles are ordered by `-published_at, -created_at`.

---

## Projects (`/projects/`)

| Method | Path | Auth | Purpose | Cache |
|--------|------|------|---------|-------|
| GET | `/projects/current/` | AllowAny | Current semester with projects | 300s |
| GET | `/projects/past/` | AllowAny | Past semesters with projects (paginated) | — |
| GET | `/projects/past-all/` | AllowAny | All past projects as a flat list | 600s |
| GET | `/projects/<uuid>/` | AllowAny | Single project detail | — |

**Current response:**
```
{
  "semester": {"year": 2025, "season": 1, "label": "Spring 2025"},
  "projects": [{...}, ...]
}
```

**Project fields:** id, class_code, team_number, team_name, project_title, organization, industry, abstract, student_names, track, presentation_order

Only published semesters (`is_published=True`) are returned. Projects within a semester are ordered by class_code and team_number.

---

## Health Check (`/health/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health/` | None | Health check (bypasses ALLOWED_HOSTS) |

**Response:**
```
{"status": "ok"}           // HTTP 200 — database reachable
{"status": "maintenance"}  // HTTP 200 — maintenance mode active
{"status": "unhealthy", "database": "unreachable"}  // HTTP 503
```

This endpoint is handled by `HealthCheckMiddleware` and bypasses Django's `ALLOWED_HOSTS` check, so load balancers can reach it regardless of the `Host` header.

---

## Events (`/event/`)

The event app has models (Event, Ticket, Question) managed via the Django admin, but **no public API endpoints** are currently defined (`event/urls.py` has empty `urlpatterns`). Event data on the frontend is served via CMS pages and Google Sheets.
