# Innovate To Grow Website

Official platform of **Innovate To Grow | University of California, Merced | School of Engineering** — a Django REST framework backend (`src/`) paired with a React 19 + TypeScript + Vite frontend (`pages/`), powering the public site, block-based CMS, projects catalog, events, and admin console.

[![CI](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Documentation

| Area | Reference |
|---|---|
| Start here | [System overview](docs/architecture/system-overview.md) · [Staff handbook](docs/staff/README.md) |
| Architecture | [Overview](docs/architecture/index.md) · [System overview](docs/architecture/system-overview.md) · [Backend](docs/architecture/backend.md) · [Frontend](docs/architecture/frontend.md) · [Request flow](docs/architecture/request-flow.md) · [Repository structure](docs/architecture/repository-structure.md) · [Integrations](docs/architecture/integrations.md) · [Code quality](docs/architecture/code-quality.md) |
| API | [Index](docs/api/index.md) · [Auth & mail](docs/api/auth-and-mail.md) · [CMS & news](docs/api/cms-and-news.md) · [Events](docs/api/events.md) · [Projects](docs/api/projects.md) · [Routing](docs/api/routing-overview.md) |
| CMS & Admin | [Index](docs/cms-admin/index.md) · [Content management](docs/cms-admin/content-management.md) · [Django admin](docs/cms-admin/django-admin.md) · [Members & mail](docs/cms-admin/member-and-mail-tools.md) · [Operations](docs/cms-admin/operations.md) · [CSS contract](docs/cms-admin/css-contract.md) · [Theme & custom CSS](docs/cms-admin/theme-and-custom-css.md) · [i2g-admin CLI](docs/cms-admin/cli-admin.md) · [Legacy event pages](docs/cms-admin/legacy-event-pages-cms-html.md) |
| Staff handbook | [Outline](docs/staff/README.md) · [2. Members & import](docs/staff/02-members-and-import.md) · [3. Blasts & email monitoring](docs/staff/03-blasts-and-email-monitoring.md) |
| Deployment | [Index](docs/deployment/index.md) · [Environments](docs/deployment/environments.md) · [Backend](docs/deployment/backend.md) · [Frontend](docs/deployment/frontend.md) · [CI/CD](docs/deployment/ci-cd.md) · [Local development](docs/deployment/local-development.md) · [Production approval](docs/deployment/production.md) · [Code scanning](docs/deployment/code-scanning.md) · [Send verification](docs/deployment/send-verification.md) · [WAF rate limits](docs/deployment/waf-rate-limits.md) · [Legacy viewer](docs/deployment/legacy-view.md) · [Operations runbook (skeleton)](docs/deployment/ops-runbook.md) |
| Integrations | [Google Sheets](docs/integrations/google-sheets/index.md) · [Microsoft Graph email](docs/integrations/microsoft-graph-email.md) · [Gmail API email](docs/integrations/gmail-api-email.md) · [Delivery rates](docs/integrations/delivery-rates.md) · [Email monitoring](docs/integrations/email-monitoring.md) · [Request limits](docs/integrations/request-limits.md) · [SES event tracking](docs/integrations/ses-event-tracking.md) · [Assistant limits](docs/integrations/assistant-limits.md) · [System Intelligence usage](docs/integrations/system-intelligence-usage.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Prerequisites

- Python 3.11+
- Node.js 22.22.2 (npm 10+; other supported releases are listed in `pages/package.json`)
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
cd src && python manage.py test --settings=config.settings.environments.local

# Frontend
cd pages && npm run lint
cd pages && npx tsc --noEmit
cd pages && npm test
cd pages && npm run build
```

---

## License

Released under the [MIT License](LICENSE). © 2025 University of California, Merced | School of Engineering.
