# AGENTS.md

## Cursor Cloud specific instructions

This is a full-stack web application: Django REST Framework backend (`src/`) + React/Vite frontend (`pages/`).

### Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Django backend | `cd src && DJANGO_SETTINGS_MODULE=core.settings.dev python3 manage.py runserver 0.0.0.0:8000` | 8000 | Must run migrations first |
| Vite frontend | `cd pages && npx vite --host 0.0.0.0 --port 5173` | 5173 | Proxies `/api`, `/media`, `/admin` to Django |

### Key caveats

- Use `python3` (not `python`) — the system only has `python3` on PATH.
- Set `DJANGO_SETTINGS_MODULE=core.settings.dev` when running Django commands; dev settings use SQLite and in-memory cache (no external services needed).
- Copy `src/.env.example` to `src/.env` before first run (the dev settings file has a hardcoded `SECRET_KEY` fallback, but some code paths read from `.env`).
- Run `cd src && DJANGO_SETTINGS_MODULE=core.settings.dev python3 manage.py migrate` before starting the backend for the first time.
- The `staticfiles.W004` warning about `/workspace/pages/public/static` not existing is harmless in dev.
- The admin login form expects an **email** field (not username) because the custom `Member` model uses email for authentication. The superuser created with `createsuperuser` uses the `--username` flag but logs in with the email provided via `--email`.

### Standard commands reference

Lint, test, build, and other common commands are documented in `.claude/CLAUDE.md` under "Common Commands".
