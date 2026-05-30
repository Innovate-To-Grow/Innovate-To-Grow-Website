---
name: frontend
description: Use this skill when writing React frontend code — pages, components, hooks, API modules, or styles under pages/.
---
# Frontend — React / TypeScript Conventions

## Architecture

- React 19, TypeScript 5.9, Vite 7, React Router v7.
- Code lives under `pages/src/` in a feature-based (vertical-slice) layout.
- Three independent React roots: `#root` (main app + router), `#menu-root` (menu), `#footer-root` (footer), mounted by `app/providers.tsx`.
- Auth state syncs across roots via the `i2g-auth-state-change` custom event + localStorage.
- A `@/*` path alias maps to `pages/src/*` (set in `tsconfig.app.json`, `vite.config.ts`, `vitest.config.ts`). Prefer `@/...` over deep relative imports.

## Directory Layout

| Directory | Purpose |
|---|---|
| `pages/src/app/` | Bootstrap + app shell: `providers.tsx`, `router.tsx`, `HomepageResolver.tsx`, `ErrorBoundary/`, `MaintenanceMode/` |
| `pages/src/routes/` | Routed page components (`<PageName>/PageName.tsx` + co-located CSS) |
| `pages/src/features/<name>/` | Domain slice: `api/`, `components/`, optional `hooks/`, `types.ts`, public `index.ts` barrel (auth, cms, events, layout, news, projects) |
| `pages/src/components/ui/` | Cross-feature presentational components (`SafeHtml/`, `SheetsDataTable/`) |
| `pages/src/lib/` | Framework-agnostic utilities: `api-client.ts`, `crypto.ts`, `time.ts`, `semester.ts`, `safeHref.ts`, `phoneRegions.ts`, `analytics.ts`, `health.ts` |
| `pages/src/hooks/` | Cross-feature React hooks (e.g. `usePageTracking`) |
| `pages/src/types/` | Shared types (`api.ts` → `PaginatedResponse<T>`) |
| `pages/src/assets/styles/shared/` | CSS design tokens and utility classes |

## API Modules

Place feature-specific API functions in `features/<name>/api/` and re-export them from the feature's `index.ts` barrel. Define TypeScript interfaces in the same module (or `types.ts`).

```typescript
// pages/src/features/<name>/api/index.ts
import { api } from '@/lib/api-client';
import { getAccessToken } from '@/features/auth';

export interface Widget {
  id: string;
  name: string;
  created_at: string;
}

function authHeaders() {
  const token = getAccessToken();
  return token ? {Authorization: `Bearer ${token}`} : {};
}

export async function fetchWidgets(): Promise<Widget[]> {
  const response = await api.get<Widget[]>('/widgets/', {
    headers: authHeaders(),
  });
  return response.data;
}
```

See `pages/src/features/events/api/index.ts` for the canonical pattern.

## Styling

- Plain CSS with CSS custom properties (no CSS-in-JS, no Tailwind).
- Design tokens in `assets/styles/shared/tokens.css` — prefixed `--itg-` (e.g., `--itg-color-primary: #0f2d52`).
- Component CSS co-located: `Widget.css` imported in `Widget.tsx`.
- Shared CSS split by concern: `tokens.css`, `layout.css`, `responsive.css`, `utilities.css`, `rich-content.css`.

## State Management

- React Context + custom hooks only. No Redux/Zustand.
- Auth: `useAuth()` from `@/features/auth`.
- Layout: `useLayout()`, `useMenu()`, `useFooter()` from `@/features/layout`.
- Data loading: custom hooks with `useState` + `useEffect` + `useCallback`.

## Pages

- Each page: `pages/src/routes/<PageName>/PageName.tsx` with co-located CSS.
- Keep page components thin — extract sections, hooks, and helpers.
- Routes defined in `pages/src/app/router.tsx` using `createBrowserRouter`; pages are lazy-loaded via deep imports (not the feature barrels) to preserve code-splitting.
- CMS catch-all route handles dynamic pages.

## Auth Flow

- Tokens stored in localStorage: `i2g_access_token`, `i2g_refresh_token`, `i2g_user`.
- Cross-root sync via `window.dispatchEvent(new Event('i2g-auth-state-change'))`.
- 401 responses trigger token refresh with in-flight deduplication (see `features/auth/api/client.ts`).

## Do NOT

- Add Redux, Zustand, or other external state libraries.
- Use CSS-in-JS or Tailwind.
- Put API functions in a central service file — use `features/<name>/api/`.
- Forget auth state sync — changes must propagate via `i2g-auth-state-change` across all three roots.
- Use relative imports that cross feature boundaries — import another feature only through its `@/features/<name>` barrel; use shared utilities from `@/lib/*`.
- Convert snake_case API responses to camelCase — keep snake_case throughout.

## Key Files

- `pages/src/lib/api-client.ts` — Axios instance (baseURL: `/api`)
- `pages/src/types/api.ts` — `PaginatedResponse<T>`
- `pages/src/features/auth/api/` — token storage, refresh flow, types
- `pages/src/features/events/api/index.ts` — canonical API module
- `pages/src/features/auth/components/AuthContext.tsx` — auth context provider
- `pages/src/features/layout/components/LayoutProvider/` — layout context
- `pages/src/assets/styles/shared/tokens.css` — design tokens
- `pages/src/app/router.tsx` — route definitions
- `pages/src/app/providers.tsx` — 3-root mount + provider stack
- `pages/vite.config.ts` — dev proxy + chunk splitting + `@` alias
- `pages/vitest.config.ts` — test configuration
