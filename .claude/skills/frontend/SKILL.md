---
name: frontend
description: Use this skill when writing React frontend code — pages, components, hooks, API modules, or styles under pages/.
---
# Frontend — React / TypeScript Conventions

## Architecture

- React 19, TypeScript 5.9, Vite 7, React Router v7.
- Code lives under `pages/src/`.
- Three independent React roots: `#root` (main app + router), `#menu-root` (menu), `#footer-root` (footer).
- Auth state syncs across roots via the `i2g-auth-state-change` custom event + localStorage.

## Directory Layout

| Directory | Purpose |
|---|---|
| `pages/src/pages/` | Routed page components (`<PageName>/PageName.tsx` + co-located CSS) |
| `pages/src/features/` | Domain code: `features/<name>/api.ts` with types + fetch functions |
| `pages/src/components/` | Shared UI components (Auth, Layout, CMS, SafeHtml, etc.) |
| `pages/src/shared/` | Auth helpers (`shared/auth/`), API client (`shared/api/`), utilities |
| `pages/src/hooks/` | Custom React hooks |
| `pages/src/styles/shared/` | CSS design tokens and utility classes |
| `pages/src/router/` | React Router configuration |
| `pages/src/services/` | Barrel re-exports from `shared/` |

## API Modules

Place feature-specific API functions in `features/<name>/api.ts`. Define TypeScript interfaces in the same file.

```typescript
// pages/src/features/<name>/api.ts
import api from '../../shared/api/client';
import {getAccessToken} from '../../services/auth';

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

See `pages/src/features/events/api.ts` for the canonical pattern.

## Styling

- Plain CSS with CSS custom properties (no CSS-in-JS, no Tailwind).
- Design tokens in `styles/shared/tokens.css` — prefixed `--itg-` (e.g., `--itg-color-primary: #0f2d52`).
- Component CSS co-located: `Widget.css` imported in `Widget.tsx`.
- Shared CSS split by concern: `tokens.css`, `layout.css`, `responsive.css`, `utilities.css`, `rich-content.css`.

## State Management

- React Context + custom hooks only. No Redux/Zustand.
- Auth: `useAuth()` from `components/Auth/AuthContext.tsx`.
- Layout: `useLayout()`, `useMenu()`, `useFooter()` from `components/Layout/LayoutProvider/`.
- Data loading: custom hooks with `useState` + `useEffect` + `useCallback`.

## Pages

- Each page: `pages/src/pages/<PageName>/PageName.tsx` with co-located CSS.
- Keep page components thin — extract sections, hooks, and helpers.
- Routes defined in `pages/src/router/index.tsx` using `createBrowserRouter`.
- CMS catch-all route handles dynamic pages.

## Auth Flow

- Tokens stored in localStorage: `i2g_access_token`, `i2g_refresh_token`, `i2g_user`.
- Cross-root sync via `window.dispatchEvent(new Event('i2g-auth-state-change'))`.
- 401 responses trigger token refresh with in-flight deduplication (see `shared/auth/client.ts`).

## Do NOT

- Add Redux, Zustand, or other external state libraries.
- Use CSS-in-JS or Tailwind.
- Put API functions in a central service file — use `features/<name>/api.ts`.
- Forget auth state sync — changes must propagate via `i2g-auth-state-change` across all three roots.
- Use relative imports that cross feature boundaries — go through `shared/`.
- Convert snake_case API responses to camelCase — keep snake_case throughout.

## Key Files

- `pages/src/shared/api/client.ts` — Axios instance (baseURL: `/api`)
- `pages/src/shared/api/types.ts` — `PaginatedResponse<T>`
- `pages/src/shared/auth/` — Token storage, refresh flow, types
- `pages/src/features/events/api.ts` — canonical API module
- `pages/src/components/Auth/AuthContext.tsx` — auth context provider
- `pages/src/components/Layout/LayoutProvider/` — layout context
- `pages/src/styles/shared/tokens.css` — design tokens
- `pages/src/router/index.tsx` — route definitions
- `pages/vite.config.ts` — dev proxy + chunk splitting
- `pages/vitest.config.ts` — test configuration
