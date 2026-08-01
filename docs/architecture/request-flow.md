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
                                                        ├─ /livez/, /readyz/, /health/ → HealthCheckMiddleware (short-circuit)
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
  └─ /api/* ──→ ALB ──→ ECS Fargate (Uvicorn)
                  │              │
                  │              ├─ /livez/ → HealthCheckMiddleware → 200 JSON, no DB
                  │              ├─ /readyz/ → HealthCheckMiddleware → 200/503 JSON, checks DB
                  │              └─ DRF views → Services → PostgreSQL + Redis
                  │
                  └─ Health probes every 30s
```

In production, the frontend is a pre-built static bundle served by Amplify/S3. API calls go through an Application Load Balancer to ECS Fargate containers running Uvicorn with bounded worker and concurrency defaults.

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

1. Frontend reads the versioned auth session from `localStorage` (`i2g_auth_session`)
2. Axios request interceptor adds `Authorization: Bearer <token>` header
3. DRF's `JWTAuthentication` validates the token
4. If expired (401), the response interceptor calls `/authn/refresh/` with the refresh token
5. On success, it updates and retries only if the same local session `generation` is still current
6. On refresh failure, it clears only that generation and dispatches `i2g-auth-state-change` (logout)

### Session bootstrap

The token record is not treated as an authoritative profile cache:

1. On startup, `bootstrapAuthSession()` snapshots the current local session generation
2. It calls authenticated `GET /authn/session/`
3. The normal response interceptor refreshes an expired access token once and retries the request
4. The backend serializes the current member and calculates `requires_profile_completion` and `next_step`
5. The frontend replaces the cached profile fields only if the original generation is still current

This generation guard prevents a slow request from an old login, logout, or another browser tab from overwriting a newer session. A rejected refresh clears the session; a transient session-endpoint failure retains a still-locally-valid access session.

### Login flow

1. Frontend fetches RSA public key from `/authn/public-key/` (cached 5 minutes)
2. User's password is encrypted client-side with Web Crypto API (RSA-OAEP)
3. `POST /authn/login/` sends `{email, password, key_id}`, where `password` contains the base64 ciphertext
4. Backend decrypts with the exact `auth-encryption` key identified by `key_id` and authenticates
5. Returns `{access, refresh, user, requires_profile_completion}`
6. Frontend stores a new versioned session generation in `localStorage` and dispatches an auth state change event
7. All three React roots pick up the new auth state

The active RSA key rotates into a new database row after one day; rotation is
checked when the public key is requested. A retired row remains decryptable
for 24 hours, is retained until 48 hours, and is then purged. Unknown and
expired key IDs fail closed. On a key/decryption error, the client clears its
public-key cache, fetches the new public key, and requires a newly encrypted
submission; the backend never tries the ciphertext against a different
private key.

### Email auth challenge flow

Used for registration, password reset, account deletion, and contact verification:

1. `POST /authn/email-auth/request-code/` — creates `EmailAuthChallenge`, sends 6-digit code via email
2. A matching verify endpoint checks the hashed code under a row lock
3. Login/registration verification conditionally consumes the challenge and returns JWTs
4. Password or deletion verification moves the challenge to `verified` and returns a hashed-at-rest `verification_token`
5. The final action conditionally consumes that token before changing protected state

Challenges expire after 10 minutes and allow at most five verification attempts. Failed attempts and expiry transitions are committed before an error response is raised. Concurrent correct requests cannot both consume the same login/registration challenge or verification token.

### SMS challenge flow

Phone authentication, contact-phone verification, password reset, and password change use `PhoneVerificationChallenge`:

1. A request endpoint creates one pending challenge for the E.164 phone number and purpose, stores only the hashed code, sends the SMS, and returns `challenge_id`
2. The client persists that opaque UUID with the in-progress flow
3. The verify endpoint locks that exact challenge, checks purpose/expiry/attempt budget, and conditionally changes `pending` to `consumed`
4. Password flows then mint the same one-time `verification_token` used by email confirmation endpoints

Verification uses only the durable database row; it does not contact AWS or require the SMS configuration that was used to send the code. For one compatibility release, verification without `challenge_id` may resolve the latest pending challenge by phone number and purpose. New clients must send `challenge_id`; it prevents two tabs or a newly requested code from verifying the wrong challenge.

### Impersonation exchange

`POST /authn/impersonate-login/` exchanges a five-minute admin-issued token for member JWTs. The token is conditionally marked used before credentials are issued. If concurrent requests race, one succeeds and every other request receives an already-used or expired error.

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

The backend's `HealthCheckMiddleware` intercepts `/livez/`, `/readyz/`, and `/health/` before security/session middleware. ECS and ALB probes use `/livez/` so database saturation does not restart otherwise healthy tasks. Deploy smoke tests and monitoring use `/readyz/` to verify database connectivity. The frontend keeps using `/health/` for maintenance status.

## Auto-login flows

Email-originated login paths bypass the normal login form:

| Path | Trigger | Backend endpoint |
|------|---------|-----------------|
| `/login-link?token=X` | Login link in campaign or ticket email | `POST /mail/login-link/` |
| `/magic-login?token=X`, `/ticket-login?token=X` | Legacy aliases — redirect to `/login-link` | — |
| `/unsubscribe-login?token=X` | Unsubscribe link in email (no login; preference-only) | `POST /authn/unsubscribe-login/` |

`/login-link` validates the token, returns JWT access/refresh tokens plus `redirect_to`, and the frontend stores them and navigates there.

## Related pages

- [Backend](backend.md) — Middleware stack and auth system details
- [Frontend](frontend.md) — Provider hierarchy and Axios interceptors
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth endpoint specifications
- [API: Routing Overview](../api/routing-overview.md) — URL organization
