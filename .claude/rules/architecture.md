# Architecture Notes

## Backend

- Django apps stay isolated by domain under `src/`.
- Thin entrypoints should delegate to services, serializers, admin helpers, or models.
- `core/settings/*.py` remain stable import targets even when implementation moves to submodules.

## Frontend

- `app/` owns bootstrap and router setup.
- `features/` owns domain code such as auth, CMS, layout, projects, events, and news.
- `shared/` owns reusable auth helpers, API clients, hooks, styles, and utilities.

## Product behavior to preserve

- Public routes and API paths stay stable.
- CMS pages still resolve by route.
- Auth state continues syncing across React roots with the `i2g-auth-state-change` event.
