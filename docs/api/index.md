# API Reference

This section documents the public API surface that the React frontend calls from `pages/`.

## Guides

- [Authentication and layout](auth-layout.md)
- [CMS, news, and projects](content.md)
- [Events and health](events-health.md)

## Common patterns

- Base URL is `/api` in local development, with Vite proxying to Django.
- Authenticated requests use JWT access tokens and refresh automatically on `401`.
- UUID primary keys are exposed as strings throughout the API.
- Paginated list responses use DRF pagination fields: `count`, `next`, `previous`, and `results`.

## Compatibility notes

- Existing endpoint paths are intentionally stable.
- Admin-only workflows remain under Django admin and are not duplicated here.
- Route-based CMS rendering still resolves pages by `route`.
