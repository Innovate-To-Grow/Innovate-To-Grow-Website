# Repository Structure

## Top-level layout

```
.
├── src/                    # Django backend (all Python code)
│   ├── core/               # Framework: settings, models, middleware, management commands
│   ├── authn/              # Authentication, Member model, contacts, admin invitations
│   ├── cms/                # CMS pages, blocks, news, analytics, menus, footer
│   ├── event/              # Events, registration, ticketing, schedule, check-in
│   ├── projects/           # Past projects, semesters, sharing
│   ├── mail/               # Email campaigns, recipient logs, magic login
│   ├── sponsors/           # Sponsor management
│   ├── manage.py           # Django management entry point
│   ├── requirements.txt    # Python dependencies
│   ├── Dockerfile          # Production container image
│   └── .env                # Local environment variables (not in version control)
├── pages/                  # React frontend (TypeScript + Vite)
│   ├── src/                # Application source
│   ├── index.html          # HTML shell with three React mount points
│   ├── package.json        # Node dependencies and scripts
│   ├── vite.config.ts      # Dev server proxy and build config
│   └── vitest.config.ts    # Test runner config
├── aws/                    # ECS task definition template
├── docs/                   # Technical documentation (this directory)
├── archive/                # Historical CSVs, exports, and backups
├── .github/workflows/      # CI/CD pipelines
├── .claude/                # Claude Code configuration and rules
├── pyproject.toml          # Ruff linter/formatter config
├── CONTRIBUTING.md         # Contributor guidelines
└── README.md               # Project overview with doc links
```

## Backend app layout

Each Django app under `src/` follows a consistent structure:

```
src/<app>/
├── models/             # or models.py — domain models
├── views/              # or views.py — API views
├── serializers/        # or serializers.py — DRF serializers
├── services/           # Business logic modules
├── admin/              # or admin.py — Django admin configuration
├── urls.py             # App URL patterns
├── tests/              # Test modules
├── templates/          # Django templates (emails, admin overrides)
├── migrations/         # Database migrations
└── apps.py             # App configuration
```

Not every app has all directories. Smaller apps like `sponsors/` use flat files instead of packages.

## Frontend source layout

```
pages/src/
├── app/                # Bootstrap: App component, Container, providers
├── router/             # Route definitions (lazy-loaded)
├── pages/              # Routed page components (HomePage, NewsPage, etc.)
├── components/         # UI components (Auth, CMS, Layout, MainMenu, Footer)
├── features/           # Domain API modules (analytics, cms, events, layout, news, projects)
├── shared/             # Cross-cutting: auth helpers, API client, hooks, utilities
├── services/           # API service barrel exports and crypto
├── styles/             # Design tokens and shared CSS
├── __tests__/          # Frontend test files
└── main.tsx            # Entry point: mounts three React roots
```

## Configuration files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Ruff config: line length 120, Python 3.11, double quotes, LF endings |
| `src/.env` | Local env vars (SECRET_KEY, DB, AWS, Google Sheets) — not committed |
| `src/.env.example` | Template for `.env` with all expected variables |
| `pages/vite.config.ts` | Dev proxy to Django, manual code-splitting chunks |
| `pages/vitest.config.ts` | jsdom environment, 30s timeout |
| `pages/tsconfig.app.json` | ES2022 target, strict mode, bundler resolution |
| `aws/task-definition.json` | ECS Fargate task template with env var placeholders |

## Related pages

- [Backend](backend.md) — Django app responsibilities and base models
- [Frontend](frontend.md) — React architecture and module boundaries
- [Deployment: Environments](../deployment/environments.md) — How config maps to each environment
