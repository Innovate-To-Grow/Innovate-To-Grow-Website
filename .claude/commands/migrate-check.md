---
description: Validate migrations like CI — makemigrations --check --dry-run and migrate --check
allowed-tools: Bash(cd src && python manage.py makemigrations --check --dry-run:*), Bash(cd src && python manage.py migrate --check:*)
---
Run the migration-validation gate from CI and report ✓/✗ for each:

1. `cd src && python manage.py makemigrations --check --dry-run --settings=config.settings.local`
   — fails if a model change has no migration. The fix is to run `makemigrations` and commit the
   **new** migration; never edit a migration already merged to `main` (the legacy-import shim in
   `config/settings/_legacy_imports.py` depends on landed migrations staying byte-stable).
2. `cd src && python manage.py migrate --check --settings=config.settings.local`
   — fails if there are unapplied migrations.

On failure, show the offending app/model. Do not generate or edit migrations unless I ask.
