# Innovate To Grow Website

Official platform of **Innovate To Grow | University of California, Merced | School of Engineering** — a Django REST framework backend (`src/`) paired with a React 19 + TypeScript + Vite frontend (`pages/`), powering the public site, block-based CMS, projects catalog, events, and admin console.

[![CI](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Documentation

| Area | Reference |
|---|---|
| Architecture | [Overview](docs/architecture/index.md) · [Backend](docs/architecture/backend.md) · [Frontend](docs/architecture/frontend.md) · [Request flow](docs/architecture/request-flow.md) · [Repository structure](docs/architecture/repository-structure.md) |
| API | [Index](docs/api/index.md) · [Auth & mail](docs/api/auth-and-mail.md) · [CMS & news](docs/api/cms-and-news.md) · [Events](docs/api/events.md) · [Projects](docs/api/projects.md) · [Routing](docs/api/routing-overview.md) |
| CMS & Admin | [Index](docs/cms-admin/index.md) · [Content management](docs/cms-admin/content-management.md) · [Django admin](docs/cms-admin/django-admin.md) · [Members & mail](docs/cms-admin/member-and-mail-tools.md) · [Operations](docs/cms-admin/operations.md) |
| Deployment | [Index](docs/deployment/index.md) · [Environments](docs/deployment/environments.md) · [Backend](docs/deployment/backend.md) · [Frontend](docs/deployment/frontend.md) · [CI/CD](docs/deployment/ci-cd.md) · [Local development](docs/deployment/local-development.md) |
| Integrations | [Google Sheets](docs/integrations/google-sheets/) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Prerequisites

- Python 3.11+
- Node.js 18 LTS or 20 LTS (npm 10+)
- SQLite 3.35+ (dev); PostgreSQL for CI and production

---

## Local development

### Backend — Django (http://localhost:8000)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
cp src/.env.example src/.env

cd src
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Frontend — Vite (http://localhost:5173)

```bash
cd pages
npm ci
npm run dev
```

The Vite dev server proxies `/api`, `/media`, and `/static` to Django on port 8000.

---

## Quality checks

Install local git hooks once to run fast checks before commit and slower Bandit/frontend checks before push:

```bash
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push --install-hooks
```

The first secrets scan downloads the pinned gitleaks release used by CI. Run `npm install` in `pages/` before pushing so the frontend hooks can use the local toolchain.

```bash
# Backend
cd src && ruff check . && ruff format --check .
cd src && python manage.py test --settings=core.settings.dev

# Frontend
cd pages && npm run lint
cd pages && npx tsc --noEmit
cd pages && npm test
cd pages && npm run build
```

---

## License

Released under the [MIT License](LICENSE). © 2025 University of California, Merced | School of Engineering.
