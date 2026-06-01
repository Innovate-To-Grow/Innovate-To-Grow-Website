---
description: Run the i2g-admin CLI client's pytest suite (cli/), which has a 100% coverage bar
allowed-tools: Bash(cd cli && pytest:*)
---
Run the CLI client's test suite and report pass/fail plus coverage:

`cd cli && pytest --cov`

This is the `cli/` package's own **pytest** suite — separate from Django's test runner. Its CI
coverage bar is 100% (`--fail-under=100` for `cli_admin`), so a coverage drop fails the gate. For
the backend half of the CLI, run instead:

`cd src && python manage.py test apps.cli_admin --settings=config.settings.local`

See the `cli-admin` skill for context. Do not modify code to chase coverage unless I ask.
