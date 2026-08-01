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
| `/login-link` (legacy aliases `/magic-login`, `/ticket-login`), `/unsubscribe-login` | Auto-login / unsubscribe from email links | |
| `/subscribe` | Newsletter subscription | |
| `*` (catch-all) | `CMSPageComponent` | Loads page content from CMS by route |

Legacy URLs (e.g., `/profile`) redirect to their current equivalents (e.g., `/account`).

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
| `auth` | `api/` | Token storage, refresh flow, login/register/email/password flows, contacts, profile, sessions |
| `cms` | `api/` | `fetchCMSPage()`, `fetchCMSPreview()`, `fetchCMSLivePreview()` |
| `events` | `api/` | Registration, tickets, schedules, phone verification |
| `layout` | `api/` | `fetchLayoutData()` with session caching |
| `news` | `api/` | `fetchNews()`, `fetchLatestNews()`, `fetchNewsDetail()` |
| `projects` | `api/` | Current/past projects, detail, sharing |

(`trackPageView()` is not a feature — it lives in `lib/analytics.ts`, with the `usePageTracking` hook in `hooks/`.)

## Shared modules

### API client (`lib/api-client.ts`)

- Plain Axios instance with `/api` base URL for public requests.
- Does not attach credentials or refresh tokens.
- Code that can carry a member session uses the auth-specific client in `features/auth/api/client.ts`.

The auth-specific client tags each request with the session generation and access token it used. On a 401 it performs one generation-guarded refresh through `/authn/refresh/`, retries once with the fresh access token, and clears only the rejected generation if recovery fails. Session-bearing event and project requests use this client; public fallbacks remain explicit.

### Auth helpers (`features/auth/api/`)

| Module | Responsibility |
|--------|---------------|
| `storage.ts` | Validate, migrate, read, update, and generation-guard the versioned `i2g_auth_session` record |
| `client.ts` | Authenticated Axios instance with deduplicated, generation-guarded refresh and one retry |
| `flows.ts` | Login, register, email auth, password reset/change, account deletion, auto-login flows |
| `contacts.ts` | Contact email and phone CRUD + verification |
| `profile.ts` | Profile read/update, image upload |
| `session.ts` | Authoritative `/authn/session/` bootstrap, guarded logout, and auto-login helpers |

### Crypto (`lib/crypto.ts`)

- Fetches RSA public key from `/authn/public-key/` (cached 5 minutes)
- Encrypts passwords with Web Crypto API (RSA-OAEP) before sending to backend
- Returns base64-encoded ciphertext + `key_id`

## Styling

The frontend uses plain CSS with a design token system.

### Token system (`src/assets/styles/shared/tokens.css`)

CSS custom properties define the design vocabulary:
- **Colors**: `--itg-color-primary` (#0f2d52), accent-gold, error, success, etc.
- **Typography**: 12 font sizes from hero (2.5rem) to label (0.8125rem)
- **Layout**: `--itg-page-max-width` (1200px), `--itg-section-gap` (2rem)
- **Shadows, borders, spacing**: Consistent tokens throughout

### CSS organization

- `src/assets/styles/shared/` — Global: tokens, layout, responsive, utilities, rich-content
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
