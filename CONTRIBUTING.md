# Contributing to the Innovate to Grow Website

Thanks for your interest in helping build the UC Merced Innovate to Grow (ITG) website. This project pairs a Django REST Framework backend (`src/`) with a React + TypeScript frontend powered by Vite (`pages/`). Please read this guide before opening a pull request so we can keep the codebase maintainable and releases predictable.

## Table of Contents
1. [Ways to Contribute](#ways-to-contribute)
2. [Project Prerequisites](#project-prerequisites)
3. [Local Environment Setup](#local-environment-setup)
4. [Development Workflow](#development-workflow)
5. [Coding Guidelines](#coding-guidelines)
6. [Testing Expectations](#testing-expectations)
7. [Database & Migrations](#database--migrations)
8. [Documentation & Changelogs](#documentation--changelogs)
9. [Pull Request Checklist](#pull-request-checklist)
10. [Getting Help](#getting-help)

---

## Ways to Contribute
- **Bug reports:** Open an issue with reproduction steps, expected vs. actual behavior, screenshots, and relevant server logs.
- **Feature proposals:** Outline the problem, the proposed solution, and any alternatives considered. Link design assets when available.
- **Code contributions:** Pick up an open issue or propose a new one. Keep pull requests narrowly scoped and well tested.
- **Documentation:** Improve README, this guide, in-code comments, or admin/editor docs under `docs/`.

---

## Project Prerequisites

| Tool | Recommended Version | Notes |
| --- | --- | --- |
| Python | 3.11 | CI, the Docker image, and Ruff all target 3.11 (Django 5.2). |
| Node.js | 22.22.2 | Other supported releases are listed in `pages/package.json`. |
| npm | 10+ | Ships with Node LTS installers. |
| SQLite | 3.35+ | Used for local dev database. |
| Git | 2.40+ | Enable `autocrlf=input` to avoid newline churn. |

---

## Local Environment Setup

Follow these steps after cloning the repository:

1. **Clone & workspace prep**
   ```bash
   git clone https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website
   cd Innovate-To-Grow-Website
   cp src/.env.example src/.env    # add secrets/separate values as needed
   ```

2. **Backend (Django REST Framework)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r src/requirements.txt
   cd src
   python manage.py migrate
   python manage.py createsuperuser   # optional but recommended
   python manage.py runserver
   ```

3. **Frontend (React + Vite)**
   ```bash
   cd pages
   npm install
   npm run dev    # starts Vite on http://localhost:5173
   ```

4. **Full-stack manual test**
   - Keep the Django dev server on port 8000 and the Vite dev server on port 5173.
   - The Vite proxy forwards `/api` and `/media` to the backend, so API calls should Just Work without extra configuration.

---

## Development Workflow

1. **Sync main:** `git checkout main && git pull upstream main`.
2. **Branch naming:** `feature/<short-desc>`, `fix/<bug-id>`, or `docs/<topic>`.
3. **Scope and commits:** Prefer small, reviewable changes. Each commit should implement a logical step and include a descriptive message (imperative mood, e.g., `Add footer serializer tests`).
4. **Keep up to date:** Rebase (`git pull --rebase upstream main`) before opening or updating a PR.
5. **Issue references:** Mention the related GitHub issue in both commit messages and PR descriptions (`Fixes #123`).
6. **Reviews:** Expect at least one reviewer to sign off. Address feedback with follow-up commits—avoid force-pushing after review unless explicitly requested.

---

## Code Style & Linting

This project uses automated code style checks in CI/CD. All pull requests must pass these checks before merging.

### Automated CI/CD Checks
On every push and pull request, GitHub Actions runs:
- **Python (Backend):** Ruff linter and formatter check
- **TypeScript (Frontend):** ESLint and TypeScript type check

### Local Linting Setup

**Option 1: Pre-commit hooks (recommended)**
```bash
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push --install-hooks
# Fast checks run before each commit; Bandit and frontend lint/type checks run before push
```
The first secrets scan downloads the pinned gitleaks release used by CI. Run `npm install` in `pages/` before pushing so the frontend hooks can use the local toolchain.

**Option 2: Manual linting**
```bash
# Backend (from project root)
pip install ruff
cd src
ruff check .           # Check for issues
ruff check . --fix     # Auto-fix issues
ruff format .          # Format code

# Frontend
cd pages
npm run lint             # ESLint (includes the hard size / complexity limits)
npx tsc --noEmit         # Type check
npm run check:structure  # Layer boundaries, import cycles, directory sizes

# Size / complexity / dependency rules (from the project root, venv active)
python scripts/ci/check_python_quality.py
python scripts/ci/check_python_dependencies.py
```
The rules, how lines and complexity are counted, and how to record a justified exception are in
[docs/architecture/code-quality.md](docs/architecture/code-quality.md). `npm run quality:report` lists the
advisory (non-blocking) findings.

---

## Coding Guidelines

### Backend (Django REST Framework)
- Follow PEP 8 style and leverage type hints where possible.
- Run `ruff check .` and `ruff format .` before committing.
- Keep business logic in `services/` modules when it does not belong directly in a model or serializer.
- Use DRF `APIView` classes with explicit method handlers and serializers (no ViewSets, generic views, or routers); set `permission_classes` on every view and throttle per view, never globally.
- When touching authentication, remember the custom `authn.Member` model (UUIDs, custom fields).
- Settings live in `src/config/settings/`: `base.py` assembles `components/`; use `config.settings.local` for development, `config.settings.test` in CI, and `config.settings.production` in deployment.
- Keep the API contract in sync with the frontend TypeScript interfaces in each feature's `api/` module (`pages/src/features/<domain>/api/`). Payloads stay snake_case.
- Respect the app dependency directions in [docs/architecture/code-quality.md](docs/architecture/code-quality.md#dependency-directions): `core` never imports a business app; register with shared machinery (e.g. `register_job_kind` in `AppConfig.ready()`) instead.

### Frontend (React + TypeScript)
- All components should be functional components with hooks; avoid class components.
- Follow the feature-based layout (`app/`, `routes/`, `features/<domain>/`, `components/`, `hooks/`, `lib/`): import another feature only through its `index.ts` barrel or its `api/` modules, and use `@/...` imports. The shared header, menu, and footer live in `features/layout`.
- Components never call Axios directly: go through the feature's `api/` module (or `@/lib/api`). Add corresponding TypeScript interfaces when backend payloads change.
- Co-locate plain CSS files with components (`Component.css`; no CSS-in-JS or Tailwind) and use the `--itg-` design tokens.
- Run `npm run lint` before submitting—ESLint enforces React hooks and TypeScript best practices.

### General
- Avoid introducing new dependencies unless necessary; document rationale in the PR.
- Include concise comments only when logic is non-obvious (per repository instructions).
- Keep secrets out of the repo. Use `.env` files and environment variables instead.

---

## Testing Expectations

| Area | Command | Notes |
| --- | --- | --- |
| Backend unit/functional tests | `cd src && python manage.py test --settings=config.settings.local` | You can scope tests with dotted paths (`python manage.py test apps.event.tests.api --settings=config.settings.local`). |
| Backend migrations | `python manage.py makemigrations && python manage.py migrate` | Required whenever models change. Commit the generated migration files. |
| Frontend linting | `cd pages && npm run lint` | Ensures TypeScript + React hooks compliance. |
| Frontend unit tests | `cd pages && npm run test:coverage` | Runs the same unit suite and coverage checks as CI. |
| Frontend type/build check | `cd pages && npm run build` | Runs `tsc -b` and the production Vite build. |
| Manual smoke test | Run both dev servers, then load http://localhost:5173 | Verify menus, content pages, and API-driven sections render without console errors. |

Please add or update automated tests when you:
- Create or change Django models, serializers, or services.
- Modify API endpoints or request/response shapes.
- Introduce new React components, hooks, or data flows.
- Fix a bug (include a regression test).

For asynchronous frontend tests, wait for the behavior being asserted. A `findBy*` query only confirms that an element exists; use `waitFor` when checking a later effect such as focus.

---

## Database & Migrations
- Never edit an existing migration that has already landed on `main`. Create a new migration instead.
- Keep migrations deterministic (no reliance on runtime data).
- The project ships no data fixtures. Seed service credentials with `python manage.py seed_service_configs` (from `src/.env`); tests build their own data.
- If your change requires seeded admin data, explain the manual steps in the PR description and update the docs if needed.

---

## Documentation & Changelogs
- Update `README.md` when setup steps or project overview change.
- Inline code comments should explain *why* rather than *what*.
- For large features, consider adding a short design note inside `docs/` and link it from the PR.

---

## Pull Request Checklist
- [ ] PR references related issue(s) and describes the change, motivation, and testing.
- [ ] Code follows the guidelines above and is scoped to a single concern.
- [ ] **CI checks pass:** All GitHub Actions workflows (linting, type checks) succeed.
- [ ] Backend: `ruff check .` and `ruff format --check .` pass, migrations added (if models changed), and `python manage.py test --settings=config.settings.local` passes; `python scripts/ci/check_python_quality.py` and `python scripts/ci/check_python_dependencies.py` pass.
- [ ] Frontend: `npm run lint`, `npm run check:structure`, and `npm run build` succeed locally.
- [ ] API contracts updated in both backend serializers and frontend TypeScript types.
- [ ] Screenshots or GIFs attached when UI changes are visible.
- [ ] Documentation updated (README, CLAUDE.md, `docs/`, or inline comments) when behavior changes.

---

## Getting Help
- **Questions:** Open a draft issue or discussion detailing the context and what you’ve tried.
- **Security reports:** Please do **not** open public issues for security vulnerabilities. Email the maintainers or the UC Merced ITG team privately.

Thank you for helping build the Innovate to Grow platform!
