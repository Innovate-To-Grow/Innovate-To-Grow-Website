# Common Commands

## Backend

```bash
cd src && python manage.py runserver
cd src && python manage.py migrate
cd src && python manage.py test --settings=core.settings.dev
cd src && ruff check .
cd src && ruff format --check .
cd src && python manage.py cms_seed
```

## Frontend

```bash
cd pages && npm ci
cd pages && npm run dev
cd pages && npm run lint
cd pages && npx tsc --noEmit
cd pages && npm run build
```

## Repository checks

```bash
python src/core/scripts/check_repo_structure.py
bash src/core/scripts/clean_local_artifacts.sh
```
