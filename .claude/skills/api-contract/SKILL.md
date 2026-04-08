---
name: api-contract
description: Use this skill when defining or consuming API endpoints between the Django backend and React frontend.
---
# API Contract — Frontend / Backend Interface

## Proxy Setup

- Vite dev server proxies `/api/*` to Django at `http://127.0.0.1:8000`, stripping the `/api` prefix.
- Frontend Axios `baseURL` is `/api` (set in `shared/api/client.ts`).
- So `api.get('/event/schedule/')` hits Vite at `/api/event/schedule/`, which proxies to Django at `/event/schedule/`.
- In production, the proxy is handled at the infrastructure level.

## Authentication

- JWT via `Authorization: Bearer <access_token>` header.
- Access token: 1h lifetime. Refresh token: 7d with rotation + blacklist.
- Frontend stores tokens in localStorage; refreshes via `/authn/refresh/`.
- Public endpoints: `permission_classes = [AllowAny]`.
- Authenticated endpoints: `permission_classes = [IsAuthenticated]`.

## Response Formats

**Success (single):** `200` or `201` — JSON object directly.

**Success (paginated list):** `200`
```json
{"count": 42, "next": "...?page=2", "previous": null, "results": [...]}
```
Frontend type: `PaginatedResponse<T>` from `shared/api/types.ts`.

**Validation error:** `400`
```json
{"field_name": ["Error message."], "other_field": ["Another error."]}
```

**Auth error:** `401` — `{"detail": "Authentication credentials were not provided."}`

**Permission error:** `403` — `{"detail": "You do not have permission to perform this action."}`

**Not found:** `404` — `{"detail": "Not found."}`

## Field Conventions

- Backend returns **snake_case** field names; frontend interfaces mirror them exactly.
- UUIDs are strings: `"id": "550e8400-e29b-41d4-a716-446655440000"`.
- Timestamps are ISO 8601 strings.
- Booleans are JSON `true`/`false`.

## Adding a New Endpoint

1. **Backend:** Create view in `src/<app>/views/`, serializer in `src/<app>/serializers/`, add `path()` in `src/<app>/urls.py`.
2. **Frontend:** Add types + API function in `pages/src/features/<name>/api.ts`.
3. **Verify** the URL path matches (frontend `/api/event/foo/` → Django `/event/foo/`).

## URL Naming

- Backend uses kebab-case: `/event/registration-options/`.
- UUID params: `<uuid:pk>` in Django, interpolated in frontend: `` `/event/my-tickets/${id}/resend-email/` ``.
- App prefix in core router: `path("event/", include("event.urls"))`.

## Auth Header Pattern (Frontend)

```typescript
function authHeaders() {
  const token = getAccessToken();
  return token ? {Authorization: `Bearer ${token}`} : {};
}

const response = await api.get<T>('/endpoint/', {headers: authHeaders()});
```

## Do NOT

- Send camelCase keys from the backend — always snake_case.
- Assume integer IDs — all PKs are UUIDs.
- Return bare strings from the backend — wrap in `{"detail": "message"}`.
- Convert snake_case to camelCase on the frontend.
- Forget trailing slashes on Django URLs — DRF expects them.

## Key Files

- `pages/vite.config.ts` — proxy rewrite rules
- `pages/src/shared/api/client.ts` — Axios instance
- `pages/src/shared/api/types.ts` — `PaginatedResponse<T>`
- `src/core/urls.py` — root URL router
- `src/event/urls.py` — canonical app URL patterns
- `src/core/settings/components/integrations/api.py` — DRF + JWT config
