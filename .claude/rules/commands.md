# Common Commands

## First-time setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
cp src/.env.example src/.env
cd src && python manage.py migrate
cd src && python manage.py createsuperuser   # prompts for email, not username

cd pages && npm ci
```

`src/requirements.txt` is a thin entrypoint that includes `requirements/local.txt`, which layers `production.txt` over `base.txt`; installing it pulls the full local toolchain (it pins Ruff). For a prod-only image install `requirements/production.txt`.

Optional but recommended — install local git hooks (fast checks pre-commit, Bandit + frontend lint/type pre-push):

```bash
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push --install-hooks
```

## Backend

All Django commands require `--settings=config.settings.local` locally (except `runserver` and `migrate` which pick it up from defaults).

```bash
cd src && python manage.py runserver
cd src && python manage.py migrate
cd src && python manage.py makemigrations
cd src && python manage.py test --settings=config.settings.local
cd src && ruff check .
cd src && ruff check . --fix      # auto-fix lint issues
cd src && ruff format --check .
cd src && ruff format .           # auto-format in place
```

### Running a single test

```bash
cd src && python manage.py test apps.authn.tests.test_api --settings=config.settings.local       # one module
cd src && python manage.py test apps.authn.tests.test_api.LoginTest --settings=config.settings.local  # one class
cd src && python manage.py test apps.authn.tests.test_api.LoginTest.test_login --settings=config.settings.local  # one method
```

### Pre-commit and SAST

```bash
pre-commit run --all-files                                  # all hooks against full tree
pre-commit run --hook-stage pre-push --all-files            # include slow pre-push hooks
cd src && bandit -r . -c ../pyproject.toml --baseline ../.bandit-baseline.json -q
cd src && python manage.py check --settings=config.settings.local
```

### Management commands

```bash
cd src && python manage.py resetdb --force                        # destructive dev-only DB reset + seed
cd src && python manage.py seed_service_configs                   # create skeleton EmailServiceConfig / optional AWSCredentialConfig rows
cd src && python manage.py verify_service_configs --strict        # confirm active DB configs before prod deploy
cd src && python manage.py createsuperuser                        # prompts for email (not username)
cd src && python manage.py sync_news --settings=config.settings.local # sync articles from UC Merced RSS feed
cd src && python manage.py loaddata cms/fixtures/footer_content.json
```

`resetdb` drops the database, regenerates migrations, migrates, and seeds an admin user + service configs. It is dev-only and has safety guards against production.

## Frontend

```bash
cd pages && npm ci
cd pages && npm run dev
cd pages && npm run lint
cd pages && npx tsc --noEmit
cd pages && npm test             # vitest
cd pages && npx vitest run path/to/file.test.ts   # one frontend test file
cd pages && npm run test:watch   # vitest watch mode
cd pages && npm run build        # runs tsc -b then vite build
cd pages && npm run e2e:install  # first-time: Playwright Chromium
cd pages && npm run e2e          # Playwright e2e (pages/e2e/*.spec.ts)
```

## CLI (`i2g-admin`)

The `cli/` package is a standalone tool with **its own pytest suite** (not Django's runner). See the `cli-admin` skill and `docs/cms-admin/cli-admin.md` for the full flow.

```bash
cd cli && pip install -e .       # installs the `i2g-admin` command (deps: typer, requests, rich)
cd cli && pytest --cov           # client test suite (per-app coverage bar: 100%)
cd src && python manage.py test apps.cli_admin --settings=config.settings.local  # backend /admin-api/ tests
cd src && python manage.py cli_admin_cleanup     # purge expired auth codes + tokens (schedule in prod)
```
