# Request Flow

How requests move through the system, from browser to backend and back.

## Local development flow

```
Browser (localhost:5173)
  │
  ├─ Static assets ──→ Vite dev server (HMR, TypeScript)
  │
  └─ /api/*, /media/*, /static/* ──→ Vite proxy ──→ Django (localhost:8000)
                                                        │
                                                        ├─ /health/ → HealthCheckMiddleware (short-circuit)
                                                        ├─ /admin/* → Unfold admin
                                                        └─ /authn/*, /cms/*, /event/*, etc. → DRF views
                                                                                                │
                                                                                                └─ Services → Database (SQLite)
```

The Vite dev server (`pages/vite.config.ts`) proxies three path prefixes to Django:
- `/api` — all REST API calls
- `/media` — uploaded files
- `/static` — Django static files (admin CSS/JS, CKEditor assets)

The backend URL is configurable via `VITE_BACKEND_URL` (defaults to `http://127.0.0.1:8000`).

## Production flow

```
Browser
  │
  ├─ Static assets ──→ AWS Amplify (CDN) ──→ S3 (built frontend)
  │
  └─ /api/* ──→ ALB ──→ ECS Fargate (Gunicorn)
                  │              │
                  │              ├─ /health/ → HealthCheckMiddleware → 200 JSON
                  │              └─ DRF views → Services → PostgreSQL + Redis
                  │
                  └─ Health probes every 30s
```

In production, the frontend is a pre-built static bundle served by Amplify/S3. API calls go through an Application Load Balancer to ECS Fargate containers running Gunicorn (4 workers, 2 threads, 120s timeout).

## API request lifecycle

### Unauthenticated request

1. Browser sends `GET /api/news/`
2. Vite proxy (dev) or ALB (prod) forwards to Django
3. Middleware stack runs (CORS, CSRF, etc.)
4. DRF router matches the URL pattern
5. View checks permissions (`AllowAny` for public endpoints)
6. Serializer formats the response
7. JSON response returned

### Authenticated request

1. Frontend reads access token from `localStorage` (`i2g_access_token`)
2. Axios request interceptor adds `Authorization: Bearer <token>` header
3. DRF's `JWTAuthentication` validates the token
4. If expired (401), the response interceptor calls `/authn/refresh/` with the refresh token
5. On success, stores new tokens and retries the original request
6. On refresh failure, clears tokens and dispatches `i2g-auth-state-change` (logout)

### Login flow

1. Frontend fetches RSA public key from `/authn/public-key/` (cached 5 minutes)
2. User's password is encrypted client-side with Web Crypto API (RSA-OAEP)
3. `POST /authn/login/` sends `{email, encrypted_password, key_id}`
4. Backend decrypts password, authenticates, rotates RSA keypair
5. Returns `{access, refresh, user, requires_profile_completion}`
6. Frontend stores tokens in `localStorage`, dispatches auth state change event
7. All three React roots pick up the new auth state

### Email auth challenge flow

Used for registration, password reset, account deletion, and contact verification:

1. `POST /authn/email-auth/request-code/` — creates `EmailAuthChallenge`, sends 6-digit code via email
2. `POST /authn/email-auth/verify-code/` — validates code, returns `verification_token`
3. Final action endpoint uses the `verification_token` to complete the operation

Challenges expire after 10 minutes. Maximum 5 verification attempts.

## CMS page resolution

The frontend catch-all route (`*`) renders `CMSPageComponent`:

1. React router matches no explicit route
2. `CMSPageComponent` extracts the current path
3. Calls `GET /api/cms/pages/{path}/`
4. Backend looks up `CMSPage` by `route` field
5. Returns page metadata + ordered `CMSBlock` records (JSON)
6. Frontend renders blocks by type (hero, text, image, cards, etc.)

## Health check and maintenance

The `HealthCheckProvider` on the frontend:

1. Calls `GET /health/` on startup
2. If the response includes `maintenance: true`, shows the maintenance overlay
3. If the request fails entirely, shows a "backend unavailable" screen
4. Polls every 10 seconds while unhealthy
5. Reloads the page on recovery (unhealthy → healthy transition)

The backend's `HealthCheckMiddleware` intercepts `/health/` before all other middleware and always returns HTTP 200 with a JSON body — this keeps ALB probes from failing during maintenance.

## Auto-login flows

Three email-originated login paths bypass the normal login form:

| Path | Trigger | Backend endpoint |
|------|---------|-----------------|
| `/ticket-login?token=X` | QR code on event ticket | `POST /event/ticket-login/` |
| `/magic-login?token=X` | Magic link in campaign email | `POST /mail/magic-login/` |
| `/unsubscribe-login?token=X` | Unsubscribe link in email | `POST /authn/unsubscribe-login/` |

Each validates the token, returns JWT access/refresh tokens, and the frontend stores them and navigates to the appropriate page.

## Related pages

- [Backend](backend.md) — Middleware stack and auth system details
- [Frontend](frontend.md) — Provider hierarchy and Axios interceptors
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth endpoint specifications
- [API: Routing Overview](../api/routing-overview.md) — URL organization
