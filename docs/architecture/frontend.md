# Frontend Architecture

The frontend is a React 19 application written in TypeScript, built with Vite, and located under `pages/`. It runs as a single-page application with three independent React roots.

## Three React roots

The HTML shell (`pages/index.html`) defines three mount points:

| Root | Mount point | Content | Has router? |
|------|-------------|---------|-------------|
| Main app | `#root` | Full SPA with page routing | Yes (BrowserRouter) |
| Menu | `#menu-root` | `MainMenu` component only | No |
| Footer | `#footer-root` | `Footer` component only | No |

**Why three roots?** The menu and footer render independently of page navigation. This avoids re-rendering them on every route change and allows them to update their auth state without a full page reload.

### Bootstrap sequence (`pages/src/main.tsx`)

Each root is created with `createRoot()` and wrapped in the appropriate providers:

```
#root:        HealthCheckProvider → AuthProvider → LayoutProvider → RouterProvider
#menu-root:   AuthProvider → LayoutProvider → MainMenu
#footer-root: LayoutProvider → Footer
```

### Cross-root auth sync

All three roots share authentication state through two mechanisms:

1. **Custom event** `i2g-auth-state-change` — dispatched by `AuthProvider` when auth state changes. All roots listen for this event on `window`.
2. **Storage event** — `localStorage` changes (tokens, user data) trigger the browser's native `storage` event, enabling cross-tab sync.

Any change to auth flow must ensure both mechanisms fire correctly.

## Router

Defined in `pages/src/router/index.tsx`. All page components are lazy-loaded with `React.lazy()`.

### Route groups

| Pattern | Component | Notes |
|---------|-----------|-------|
| `/` | `HomepageResolver` | Dynamically loads homepage from `SiteSettings.homepage_route` |
| `/login`, `/register`, `/account`, etc. | Auth pages | Under `components/Auth/pages/` |
| `/news`, `/news/:id` | News list and detail | |
| `/current-projects`, `/past-projects`, `/projects/:id` | Project pages | |
| `/event-registration`, `/events/:eventSlug`, `/schedule` | Event pages | |
| `/ticket-login`, `/magic-login`, `/unsubscribe-login` | Auto-login from email links | |
| `/subscribe` | Newsletter subscription | |
| `*` (catch-all) | `CMSPageComponent` | Loads page content from CMS by route |

Legacy URLs (e.g., `/profile`) redirect to their current equivalents (e.g., `/account`).

## Key providers

### HealthCheckProvider

`src/components/MaintenanceMode/HealthCheckProvider.tsx`

- Checks `/health/` on startup (5-second timeout)
- Polls every 10 seconds when the backend is unhealthy
- Renders a `MaintenanceMode` overlay when the backend is down
- Reloads the page when transitioning from unhealthy to healthy
- Supports maintenance bypass with a password

### AuthProvider

`src/components/Auth/AuthContext.tsx`

- Manages user state, authentication status, and profile completion requirement
- Provides 20+ auth action methods (login, register, email flows, password management, etc.)
- Listens for `i2g-auth-state-change` and `storage` events

### LayoutProvider

`src/components/Layout/LayoutProvider/LayoutProvider.tsx`

- Fetches menus and footer from `/layout/` endpoint
- Caches in `sessionStorage` with version key (`v1`)
- Revalidates every 60 seconds or on window focus/visibility change

## Feature modules

Each feature under `pages/src/features/` exports API functions for its domain:

| Feature | File | Key exports |
|---------|------|-------------|
| `analytics` | `api.ts` | `trackPageView()` |
| `cms` | `api.ts` | `fetchCMSPage()`, `fetchCMSPreview()`, `fetchCMSLivePreview()` |
| `events` | `api.ts` | Registration, tickets, schedules, phone verification |
| `layout` | `api.ts` | `fetchLayoutData()` with session caching |
| `news` | `api.ts` | `fetchNews()`, `fetchLatestNews()`, `fetchNewsDetail()` |
| `projects` | `api.ts` | Current/past projects, detail, sharing |

## Shared modules

`pages/src/shared/` contains cross-cutting concerns:

### API client (`shared/api/client.ts`)

- Axios instance with `/api` base URL
- **Request interceptor**: Injects `Authorization: Bearer <token>` from `localStorage`
- **Response interceptor**: On 401, attempts token refresh via `/authn/refresh/`, then retries the original request

### Auth helpers (`shared/auth/`)

| Module | Responsibility |
|--------|---------------|
| `storage.ts` | localStorage keys (`i2g_access_token`, `i2g_refresh_token`, `i2g_user`), get/set/clear functions |
| `client.ts` | Authenticated Axios instance with automatic token refresh |
| `flows.ts` | Login, register, email auth, password reset/change, account deletion, auto-login flows |
| `contacts.ts` | Contact email and phone CRUD + verification |
| `profile.ts` | Profile read/update, image upload |
| `session.ts` | Auto-login helpers (ticket, magic link, unsubscribe) |

### Crypto (`services/crypto.ts`)

- Fetches RSA public key from `/authn/public-key/` (cached 5 minutes)
- Encrypts passwords with Web Crypto API (RSA-OAEP) before sending to backend
- Returns base64-encoded ciphertext + `key_id`

## Styling

The frontend uses plain CSS with a design token system.

### Token system (`src/styles/shared/tokens.css`)

CSS custom properties define the design vocabulary:
- **Colors**: `--itg-color-primary` (#0f2d52), accent-gold, error, success, etc.
- **Typography**: 12 font sizes from hero (2.5rem) to label (0.8125rem)
- **Layout**: `--itg-page-max-width` (1200px), `--itg-section-gap` (2rem)
- **Shadows, borders, spacing**: Consistent tokens throughout

### CSS organization

- `src/styles/shared/` — Global: tokens, layout, responsive, utilities, rich-content
- `src/index.css` — Imports shared styles, sets up body and app-layout
- Component-scoped `.css` files alongside each component
- CMS-specific styles in `components/CMS/styles/` and `components/CMS/page-styles/`

## Testing

- **Framework**: Vitest + @testing-library/react
- **Config**: `pages/vitest.config.ts` — jsdom environment, 30-second timeout
- **Test files**: `pages/src/__tests__/` — router smoke tests, lazy route resolution, barrel export integrity, CSS import validation

## Related pages

- [Backend](backend.md) — The API this frontend consumes
- [Request Flow](request-flow.md) — End-to-end data path
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth endpoint details
- [Deployment: Frontend](../deployment/frontend.md) — Amplify build and deployment
