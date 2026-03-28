# CMS, News, and Projects API

## CMS pages

- `GET /cms/pages/<route>/` returns the published CMS page for a route.
- `GET /cms/pages/` with a preview token returns preview content for admins.
- Each page includes `slug`, `route`, `title`, `page_css_class`, `meta_description`, `blocks`, and optional preview expiry metadata.
- Block rendering is delegated to the frontend `features/cms` layer.

## Google Sheets display proxy

- `GET /sheets/<slug>/` returns preconfigured event or project sheet data.
- Sheets support stale-while-revalidate caching.
- The response shape depends on the configured display mode for the source.

## News

- `GET /news/` returns paginated articles.
- `GET /news/<id>/` returns article detail.
- Syncing inbound feeds remains an internal admin and management-command workflow.

## Projects

- `GET /projects/current/` returns the current semester and project rows.
- `GET /projects/past/` returns paginated historical semesters.
- `GET /projects/past-all/` returns the full historical table for archive pages.
- `GET /projects/<id>/` returns one project detail record.
- `POST /projects/past-shares/` creates a shareable filtered snapshot.
- `GET /projects/past-shares/<id>/` resolves a saved shared snapshot.
