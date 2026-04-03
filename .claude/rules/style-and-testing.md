# Style and Testing

## Backend

- Use Ruff for linting and formatting (config in `pyproject.toml`).
- Line length: 120. Target: Python 3.11. Double quotes, LF endings.
- Enabled rule sets: E, W, F, I, B, C4, UP, DJ. E501 is disabled (length handled by formatter).
- Also ignored: B008 (function calls in defaults — needed for Django), B904, DJ001, DJ007, DJ012.
- Known first-party imports: core, authn, cms, event, news, projects, mail, sheets, sponsors.
- Star imports (`F403`/`F405`) are allowed in `settings/` files; unused imports (`F401`) are allowed in `__init__.py`; unused variables (`F841`) are allowed in test files.
- Migrations are excluded from linting.
- Keep command, view, and serializer entrypoints thin.
- Prefer subpackages over growing new oversized modules.

## Frontend

- Keep feature pages thin by extracting hooks, helpers, and sections.
- Keep shared CSS split by concern instead of expanding broad catch-all stylesheets.
- Prefer feature-local APIs over a central dumping-ground service module.

## Validation

- Backend: `ruff check .`, `ruff format --check .`, `python manage.py check`, and targeted Django tests.
- Frontend: `npm run lint`, `npx tsc --noEmit`, `npm test` (vitest), and `npm run build`.
