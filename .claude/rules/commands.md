# Common Commands

## Backend

```bash
cd src && python manage.py runserver
cd src && python manage.py migrate
cd src && python manage.py test --settings=core.settings.dev
cd src && ruff check .
cd src && ruff format --check .
```

### Running a single test

```bash
cd src && python manage.py test authn.tests.test_api --settings=core.settings.dev       # one module
cd src && python manage.py test authn.tests.test_api.LoginTest --settings=core.settings.dev  # one class
cd src && python manage.py test authn.tests.test_api.LoginTest.test_login --settings=core.settings.dev  # one method
```

## Frontend

```bash
cd pages && npm ci
cd pages && npm run dev
cd pages && npm run lint
cd pages && npx tsc --noEmit
cd pages && npm run build
```
