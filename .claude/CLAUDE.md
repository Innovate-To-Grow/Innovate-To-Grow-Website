# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repository guidance is split into short references so local instructions stay easy to scan.

## Quick links

- [Commands](rules/commands.md)
- [Architecture](rules/architecture.md)
- [Workflow](playbooks/development.md)
- [Style and testing](rules/style-and-testing.md)
- [Environment notes](rules/environment.md)

## Working assumptions

- Backend lives under `src/` (Django 5.2 + DRF).
- Frontend lives under `pages/` (React 19 + TypeScript + Vite).
- Active docs live under `docs/`.
- Historical material lives under `archive/`.
- Dev database is SQLite; prod is PostgreSQL.
- Settings use `--settings=core.settings.dev` for local work.
- Vite dev server (port 5173) proxies `/api`, `/media`, `/static` to Django (port 8000).
- Ruff: line length 120, target Python 3.11, double quotes, LF endings.
- Deployment: Amplify (frontend); CI settings: `core.settings.ci`.
