# System Architecture

The ITG platform is a Django backend plus a React/Vite frontend with shared deployment and admin tooling.

## Guides

- [Backend architecture](backend.md)
- [Frontend architecture](frontend.md)
- [Platform and operations](platform.md)
- [Repository structure and naming](repo-structure.md)

## Snapshot

- Backend: Django 5.2, DRF, SQLite for local development, PostgreSQL in production.
- Frontend: React 19, TypeScript 5.9, Vite 7, three coordinated React roots.
- Storage and integrations: Redis, S3-compatible static/media storage, Google Sheets, Gmail API, AWS SES.
- Content model: CMS pages, menus, footer content, and site settings are managed in Django admin.
