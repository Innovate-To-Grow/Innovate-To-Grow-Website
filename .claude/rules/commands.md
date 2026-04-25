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

Optional but recommended — install local git hooks (fast checks pre-commit, Bandit + frontend lint/type pre-push):

```bash
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push --install-hooks
```

## Backend

All Django commands require `--settings=core.settings.dev` locally (except `runserver` and `migrate` which pick it up from defaults).

```bash
cd src && python manage.py runserver
cd src && python manage.py migrate
cd src && python manage.py makemigrations
cd src && python manage.py test --settings=core.settings.dev
cd src && ruff check .
cd src && ruff check . --fix      # auto-fix lint issues
cd src && ruff format --check .
cd src && ruff format .           # auto-format in place
```

### Running a single test

```bash
cd src && python manage.py test authn.tests.test_api --settings=core.settings.dev       # one module
cd src && python manage.py test authn.tests.test_api.LoginTest --settings=core.settings.dev  # one class
cd src && python manage.py test authn.tests.test_api.LoginTest.test_login --settings=core.settings.dev  # one method
```

### Pre-commit and SAST

```bash
pre-commit run --all-files                                  # all hooks against full tree
pre-commit run --hook-stage pre-push --all-files            # include slow pre-push hooks
cd src && bandit -r . -c ../pyproject.toml --baseline ../.bandit-baseline.json -q
cd src && python manage.py check --settings=core.settings.dev
```

### Management commands

```bash
cd src && python manage.py resetdb --force                        # destructive dev-only DB reset + seed
cd src && python manage.py seed_service_configs                   # create EmailServiceConfig/SMSServiceConfig from .env
cd src && python manage.py createsuperuser                        # prompts for email (not username)
cd src && python manage.py sync_news --settings=core.settings.dev # sync articles from UC Merced RSS feed
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
```
