# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repository guidance is split into short references so local instructions stay easy to scan.

## Quick links

- [Commands](rules/commands.md)
- [Architecture](rules/architecture.md)
- [Workflow](playbooks/development.md)
- [Style and testing](rules/style-and-testing.md)
- [Environment notes](rules/environment.md)

## Personal overrides

- `CLAUDE.local.md` (gitignored) — drop personal preferences, scratch notes, and machine-specific reminders here. It loads alongside `CLAUDE.md` but is never committed.
- `.claude/settings.local.json` (gitignored) — personal permissions / hooks. Never check in credentials, even though the file is gitignored — use `~/.aws/credentials` or `aws sso login` for AWS.

## Working assumptions

- Backend lives under `src/` (Django 5.2 + DRF).
- Frontend lives under `pages/` (React 19 + TypeScript + Vite).
- Active docs live under `docs/`: architecture (`docs/architecture/`), API contracts (`docs/api/`), CMS & admin operations (`docs/cms-admin/`), deployment (`docs/deployment/`), integrations (`docs/integrations/`). Consult these before re-deriving things from code.
- Historical material lives under `archive/`.
- Dev database is SQLite; prod is PostgreSQL.
- Settings use `--settings=core.settings.dev` for local work.
- Vite dev server (port 5173) proxies `/api`, `/media`, `/static` to Django (port 8000).
- Ruff: line length 120, target Python 3.11, double quotes, LF endings.
- Deployment: Amplify (frontend ZIP upload to S3 via AWS Amplify API); CI settings: `core.settings.ci`.
- Admin theme: Unfold (all admin classes inherit from `core.admin.BaseModelAdmin` or `ReadOnlyModelAdmin`, not stock `ModelAdmin`).

## Key gotchas

- Do NOT set `DEFAULT_THROTTLE_CLASSES` globally — it breaks tests at 127.0.0.1.
- `Member` PK is a UUID, not an integer. All models using `ProjectControlModel` have UUID PKs.
- `objects` manager excludes soft-deleted rows; use `all_objects` to include them.
- Three independent React roots (`#root`, `#menu-root`, `#footer-root`) share auth state via the `i2g-auth-state-change` custom event — changes to auth flow must propagate to all three.
- Custom `createsuperuser` command prompts for email (not username). Use `--email` for non-interactive mode.
- Settings component import order matters: `environment` → `django` → `admin` → `api` → `editor` → `production`.
- Never edit an existing migration that has landed on `main`. Create a new migration instead.
- Pre-push hooks run Bandit (backend) and `npm run lint` + `tsc --noEmit` (frontend). A `git push` can fail even after a clean commit. Run `npm install` in `pages/` before pushing so the hooks find the toolchain.
