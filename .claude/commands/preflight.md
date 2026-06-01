---
description: Run the full local CI gate (ruff, bandit, Django tests, frontend lint/type/vitest) before pushing
allowed-tools: Bash(cd src && ruff check .), Bash(cd src && ruff format --check .), Bash(cd src && bandit:*), Bash(cd src && python manage.py test:*), Bash(cd pages && npm run lint), Bash(cd pages && npx tsc --noEmit), Bash(cd pages && npx vitest run:*)
---
Run this project's local CI gate and report a concise ✓/✗ summary per step. Run each command
from the repository root (use a subshell like `(cd src && …)` or an absolute `cd` so the working
directory does not drift between steps). Stop at the first failure and surface its output — do not
attempt fixes unless I ask.

Backend:
1. `cd src && ruff check .`
2. `cd src && ruff format --check .`
3. `cd src && bandit -r . -c ../pyproject.toml --baseline ../.bandit-baseline.json -q`
4. `cd src && python manage.py test --settings=config.settings.local`

Frontend:
5. `cd pages && npm run lint`
6. `cd pages && npx tsc --noEmit`
7. `cd pages && npx vitest run`

These mirror `.github/workflows/ci.yml`. Note CI runs the Django suite on PostgreSQL via
`config.settings.test`; locally we use SQLite via `config.settings.local`, so a DB-specific failure
can still slip past. Migrations are validated separately — run `/migrate-check` for that.
End with a one-line pass/fail table.
