# Frontend Architecture

## Runtime shape

- `pages/index.html` defines three roots: the main app, the menu, and the footer.
- The app root owns routing and long-lived providers.
- The menu and footer roots reuse shared providers where needed but render independently.

## Source layout

- `app/` contains bootstrap code, router assembly, and top-level providers.
- `features/` groups domain code such as auth, CMS, layout, projects, events, and news.
- `shared/` contains reusable API clients, auth utilities, styles, hooks, and generic UI helpers.

## Rendering model

- CMS-managed routes render through `CMSPageComponent`.
- Data-driven routes have dedicated feature pages for news, projects, registration, and archive flows.
- The homepage is resolved dynamically from `homepage_route`.

## API access

- Shared HTTP clients live in `shared/api`.
- Feature-specific API modules live with the feature that owns the data contract.
- Cached layout data and auth refresh behavior stay centralized.
