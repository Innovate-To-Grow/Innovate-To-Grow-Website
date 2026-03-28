# Style and Testing

## Backend

- Use Ruff for linting and formatting.
- Keep command, view, and serializer entrypoints thin.
- Prefer subpackages over growing new oversized modules.

## Frontend

- Keep feature pages thin by extracting hooks, helpers, and sections.
- Keep shared CSS split by concern instead of expanding broad catch-all stylesheets.
- Prefer feature-local APIs over a central dumping-ground service module.

## Validation

- Backend: `ruff check .`, `ruff format --check .`, `python manage.py check`, and targeted Django tests.
- Frontend: `npm run lint`, `npx tsc --noEmit`, and `npm run build`.
