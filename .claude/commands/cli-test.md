---
description: Run the i2g-admin CLI client's pytest suite (cli/)
allowed-tools: Bash(cd cli && pytest:*)
---
Run the CLI client's test suite and report pass/fail plus coverage:

`cd cli && pytest --cov`

This is the `cli/` package's own **pytest** suite — separate from Django's test runner — and it is
**not** run or gated in CI (its `pyproject.toml` sets no `fail_under`). The `--fail-under=100` gate
in CI applies to the **backend** Django app `apps.cli_admin` (+ the shared `safe_orm` service), run via:

`cd src && python manage.py test apps.cli_admin --settings=config.settings.local`

So run both for full CLI coverage. See the `cli-admin` skill for context. Do not modify code to
chase coverage unless I ask.
