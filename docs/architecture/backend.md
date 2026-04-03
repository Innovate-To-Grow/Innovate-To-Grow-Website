//# Backend Architecture

## App map

- `core`: settings, health middleware, shared model infrastructure, and admin helpers.
- `pages`: CMS pages, layout data, Google Sheets display sources, and related admin tooling.
- `authn`: member accounts, JWT auth, verification flows, contact info, and admin login helpers.
- `event`: registration models, ticket generation, and attendee APIs.
- `news`: article ingestion, feed sources, and public news APIs.
- `projects`: semester and project data plus archive and sharing APIs.
- `sponsors`: supporting integrations and public read APIs.

## Routing

`src/core/urls.py` remains the single routing hub for admin, REST APIs, CMS preview, auth, and health routes.

## Data conventions

- Primary keys use UUIDs.
- Soft delete and version history come from `ProjectControlModel`.
- Public endpoints must opt into `AllowAny`; authenticated defaults stay locked down.

## Settings

- `core/settings/base.py`, `dev.py`, `ci.py`, and `prod.py` remain the import entrypoints.
- Shared setting fragments now live behind those thin entry files to keep deployment paths stable.
