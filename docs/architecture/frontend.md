# Frontend Architecture

The frontend is a React 19 application written in TypeScript, built with Vite, and located under `pages/`. It runs as a single-page application with four independently mounted React roots.

## React roots

The HTML shell (`pages/index.html`) defines four mount points:

| Root | Mount point | Content | Has router? |
|------|-------------|---------|-------------|
| Main app | `#root` | Full SPA with page routing | Yes (BrowserRouter) |
| Menu | `#menu-root` | `MainMenu` component only | No |
| Footer | `#footer-root` | `Footer` component only | No |
| Assistant | `#chatbot-root` | Public floating assistant widget | No |

**Why separate roots?** The menu, footer, and assistant render independently of page navigation. This avoids re-rendering the page shell on every route change and allows the menu to update its auth state without a full page reload.

### Bootstrap sequence (`pages/src/main.tsx`)

Each root is created with `createRoot()` and wrapped in the appropriate providers:

```
#root:        HealthCheckProvider → AuthProvider → LayoutProvider → RouterProvider
#menu-root:   AuthProvider → LayoutProvider → MainMenu
#footer-root: LayoutProvider → Footer
#chatbot-root: AssistantWidget
```

### Cross-root auth sync

The main and menu roots share authentication state through two mechanisms:

1. **Custom event** `i2g-auth-state-change` — dispatched after a local auth-session change so separate roots in the same window resynchronize.
2. **Storage event** — changes to the `i2g_auth_session` localStorage record trigger the browser's native `storage` event in other tabs.

Any change to auth flow must ensure both mechanisms fire correctly.

### Persisted session and startup bootstrap

Authentication is stored as one versioned localStorage record named `i2g_auth_session`. Version 1 contains:

- `generation` — a unique identifier for this login/session incarnation
- `access` and `refresh` — the JWT pair
- `user` — the last serialized user snapshot
- `requires_profile_completion` — the last known routing flag

`storage.ts` validates this record before use and performs a one-time migration from the former split-key format. New code must read and write the versioned record through the storage helpers rather than introduce another token or user key.

The persisted user fields are a startup hint, not authoritative account state. Each `AuthProvider` begins in an initializing state, calls `bootstrapAuthSession()`, and does not render its children until bootstrap finishes. Bootstrap sends authenticated `GET /authn/session/`; the backend response supplies the authoritative current user and profile-completion state.

Every request, refresh, bootstrap, logout, and session update is guarded by the session `generation` (and, where needed, the exact refresh/access token). A slow response from an old login cannot overwrite or clear a newer login from the same tab or another tab. Refreshes are deduplicated per generation, retry a failed authenticated request at most once, and discard the result if the active generation changed while the refresh was in flight.

## Router

Defined in `pages/src/app/router.tsx`. All page components are lazy-loaded with `React.lazy()`.

### Route groups

| Pattern | Component | Notes |
|---------|-----------|-------|
| `/` | `HomepageResolver` | Dynamically loads homepage from `SiteSettings.homepage_route` |
| `/login`, `/register`, `/account`, etc. | Auth pages | Under `features/auth/components/pages/` |
| `/news`, `/news/:id` | News list and detail | |
| `/current-projects`, `/past-projects`, `/projects/:id` | Project pages | |
| `/event-registration`, `/events/:eventSlug`, `/schedule` | Event pages | |
| `/login-link` (legacy aliases `/magic-login`, `/ticket-login`) | Auto-login from email links | |
| `/unsubscribe-login` | Retired: `<Navigate to="/account" replace/>` | Old unsubscribe emails. Drops the token (query and fragment) and calls no API; newsletter unsubscribe links point at the backend page `/mail/unsubscribe/{token}/` |
| `/subscribe` | Newsletter subscription | Signs in through the email or phone code flows (`source=subscribe`), then edits the per-address `subscribe` flags; there is no subscribe endpoint |
| `*` (catch-all) | `CMSPageComponent` | Loads page content from CMS by route |

Legacy URLs (e.g., `/profile`) redirect to their current equivalents (e.g., `/account`).

**Emailed login links.** A `/login-link` that cannot be used (expired, already used, invalid, missing, or the server could not be reached) is not an error. The page shows an informational notice and an inline email-code sign-in: the email address, then the 6-digit code via `VerifyEmailPageContent` with `flow="login"`, whose code field takes focus when the step opens. It stays on `/login-link` because `/login` and `/verify-email` redirect an already signed-in browser to `/account`.

The fallback uses the existing-accounts `login` code flow (`requestLoginCode` and `verifyLoginCode`), not the unified email-auth flow. That flow issues a code only to an existing, active member and answers every other address with the same generic message, so the page always moves on to the code step and reveals nothing about the address. The unified flow would create a pending account for a mistyped address and sign the visitor in as that new member.

The code step opens with the server's own acknowledgement of the request (for the login flow, the same generic sentence for every address) as an info message (`role="status"`), and a hint under the code field: "Didn't get a code? Check the address above or go back to correct it." The page never words the acknowledgement itself, so it cannot say more than the server does; a response without a usable message shows the hint alone. Resending replaces the message with the new response, and Back returns to the email step, which starts the next request afresh. The host hands both to `VerifyEmailPageContent` through the optional `initialMessage` (which seeds the step's message) and `hint` (which is forwarded to `VerifyEmailView`) props; without them `/verify-email` renders exactly as before. The code field is described by the message and the hint (`aria-describedby`), because it holds focus when they appear and a live region inserted with its text is not reliably announced.

The code sign-in replaces the stored session. It lands on the link's own `redirect_to` when the backend supplies a safe one (otherwise `/account`). A token kept in the sessionStorage handoff for a retryable failure (5xx, network, or a 429 from an edge proxy or WAF, since no backend IP throttle answers this endpoint any more) is dropped once the code step opens and again after the code signs the visitor in, so a later bare `/login-link` in the same tab cannot replay it and swap the account. Retry and Back keep using the token held in memory.

Two cases do not get the fallback straight away. An already-used link in a browser that holds a session continues to `/account`, but only after `bootstrapAuthSession()` confirms the session is not dead; a dead one is cleared and the visitor gets the code sign-in, aimed at the link's destination. A browser that cannot store the new session shows a plain error, since a code sign-in could not store one either.

## Key providers

### HealthCheckProvider

`src/app/MaintenanceMode/HealthCheckProvider.tsx`

- Checks `/health/` on startup (5-second timeout)
- Polls every 10 seconds when the backend is unhealthy
- Renders a `MaintenanceMode` overlay when the backend is down
- Reloads the page when transitioning from unhealthy to healthy
- Supports maintenance bypass with a password

### AuthProvider

`src/features/auth/components/AuthContext.tsx`

- Manages user state, authentication status, and profile completion requirement
- Gates its children during the asynchronous authoritative session bootstrap
- Provides 20+ auth action methods (login, register, email flows, password management, etc.)
- Listens for `i2g-auth-state-change` and `storage` events

### LayoutProvider

`src/features/layout/components/LayoutProvider/LayoutProvider.tsx`

- Fetches menus and footer from `/layout/` endpoint
- Caches in `sessionStorage` with version key (`v1`)
- Revalidates every 60 seconds or on window focus/visibility change

## Feature modules

Each feature under `pages/src/features/` is a vertical slice (`api/`, `components/`, optional `hooks/`, `types.ts`, public `index.ts` barrel) and exposes API functions for its domain:

| Feature | Module | Key exports |
|---------|--------|-------------|
| `assistant` | `api/`, `utils/` | `fetchAssistantConfig()`, `sendAssistantMessage()`, visitor-token storage |
| `auth` | `api/` | Token storage, refresh flow, login/register/email/password flows, contacts, profile, sessions |
| `cms` | `api/` | `fetchCMSPage()`, `fetchCMSPreview()`, `fetchCMSLivePreview()` |
| `events` | `api/` | Registration, tickets, schedules, phone verification |
| `layout` | `api/` | `fetchLayoutData()` with session caching |
| `news` | `api/` | `fetchNews()`, `fetchLatestNews()`, `fetchNewsDetail()` |
| `projects` | `api/` | Current/past projects, detail, sharing |

(`trackPageView()` is not a feature — it lives in `lib/api/analytics.ts`, with the `usePageTracking` hook in `hooks/`.)

### Visitor identities (assistant and page views)

Campus users share one public IP, so the backend tells browsers apart by two values the frontend keeps in `localStorage`. Neither is a credential, and both fall back to an in-memory copy when storage is unavailable.

| Value | Key | Source | Sent as |
|-------|-----|--------|---------|
| Assistant visitor token | `itg-assistant-visitor` | Signed by the backend: taken from `GET /assistant/config/` when none is held, and replaced by any `visitor_token` a chat response (including a `429`) hands back | `visitor_token` in the `POST /assistant/chat/` body |
| Page-view visitor id | `i2g_visitor_id` | A random UUID generated in the browser | `visitor_id` in the `POST /analytics/pageview/` body |

`sendAssistantMessage()` re-sends a message once when a `429` handed back a replacement token (the request was judged in the bucket shared by token-less callers). Any other `429` shows "The assistant has reached its usage limit for now. Please try again later.", which may be the site-wide budget, so it does not blame the visitor. Both fields are optional on the wire: an older backend ignores them and a newer backend accepts requests without them, so frontend and backend can deploy in either order. Limits are described in [Assistant and AI search limits](../integrations/assistant-limits.md).

## Shared modules

### API client (`lib/api/api-client.ts`)

- Plain Axios instance with `/api` base URL for public requests.
- Does not attach credentials or refresh tokens.
- Code that can carry a member session uses the auth-specific client in `features/auth/api/client.ts`.

The auth-specific client tags each request with the session generation and access token it used. On a 401 it performs one generation-guarded refresh through `/authn/refresh/`, retries once with the fresh access token, and clears only the rejected generation if recovery fails. Session-bearing event and project requests use this client; public fallbacks remain explicit.

**Opting out with `skipAuth`.** Endpoints that authenticate by a one-time credential in the request body (the emailed login link and impersonation tokens, and the emailed-code exchanges: email-auth-link, unified email-auth and login code verification) pass `{skipAuth: true}` as the axios request config. Such a request sends no `Authorization` header, is never tagged with a session, and a failure never refreshes, retries, or clears the stored session. Without it, an expired or deleted-member bearer left over from an earlier account is rejected before the backend reads the token, the emailed link is reported as invalid, and the failed refresh can destroy the stored session. Use it only for such credential exchanges, and only where the backend view ignores JWT authentication; every call that acts as the signed-in member keeps the default behaviour. The credential-less anonymous sends (the send-verification challenge and status lookups, and the code requests) are not `skipAuth`: they may carry a stale bearer, and they stay safe only because their backend views set `authentication_classes = []`.

### Auth helpers (`features/auth/api/`)

| Module | Responsibility |
|--------|---------------|
| `storage.ts` | Validate, migrate, read, update, and generation-guard the versioned `i2g_auth_session` record |
| `client.ts` | Authenticated Axios instance with deduplicated, generation-guarded refresh and one retry |
| `flows.ts` | Login, register, email auth, password reset/change, account deletion, auto-login flows |
| `contacts.ts` | Contact email and phone CRUD + verification |
| `profile.ts` | Profile read/update, image upload |
| `session.ts` | Authoritative `/authn/session/` bootstrap, guarded logout, and auto-login helpers (login responses are shape-checked before they are stored) |
| `loginLinkFailure.ts` | Pure classifier for a failed login-link exchange (used, expired, invalid, retryable, session not saved) and its safe `redirect_to` |
| `errors.ts` | `SessionNotSavedError` (storage refused the session) and `MalformedLoginResponseError` (a 2xx body that is not a login) |

### Sign-in refusals (`features/auth/components/context/shared.ts`)

`getAuthErrorMessage()` turns a failed auth request into the text a form shows: a safe `detail` string first, then the other safe strings in the body, then a generic client-error or server-error line. A body that is not JSON (plain text or an HTML page from an edge proxy or WAF) is never read as text: it gets the same status-based line. Nothing in it depends on the visitor's network. The one code it reads is `login_locked`: the password sign-in answers HTTP 429 with it once that account has too many recent failed attempts (the block follows the account, not the IP address, so it does not affect other people on the same campus network). The form shows the server's `detail`, which already suggests signing in with an email code, and falls back to the same sentence when the body carries no usable `detail`. The "Sign in with a verification code" switch stays directly under the Sign In button. A 429 with any other code (a destination cooldown or an SMS throttle) keeps the generic mapping.

### Crypto (`lib/security/crypto.ts`)

- Fetches RSA public key from `/authn/public-key/` (cached 5 minutes)
- Encrypts passwords with Web Crypto API (RSA-OAEP) before sending to backend
- Returns base64-encoded ciphertext + `key_id`

## Styling

The frontend uses plain CSS with a design token system.

### Token system (`src/assets/tokens.css`)

CSS custom properties define the design vocabulary:
- **Colors**: `--itg-color-primary` (#0f2d52), accent-gold, error, success, etc.
- **Typography**: 12 font sizes from hero (2.5rem) to label (0.8125rem)
- **Layout**: `--itg-page-max-width` (1200px), `--itg-section-gap` (2rem)
- **Shadows, borders, spacing**: Consistent tokens throughout

### CSS organization

- `src/components/` — Shared presentational components (SafeHtml, SheetsDataTable)
- `src/assets/` — Global: tokens, layout, responsive, utilities, rich-content
- `src/index.css` — Imports shared styles, sets up body and app-layout
- Component-scoped `.css` files alongside each component

## Testing

- **Framework**: Vitest + @testing-library/react
- **Config**: `pages/vitest.config.ts` — jsdom environment, 30-second timeout
- **Test files**: `pages/src/__tests__/` — router smoke tests, lazy route resolution, barrel export integrity, CSS import validation

## Related pages

- [Backend](backend.md) — The API this frontend consumes
- [Request Flow](request-flow.md) — End-to-end data path
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth endpoint details
- [Deployment: Frontend](../deployment/frontend.md) — Amplify build and deployment
