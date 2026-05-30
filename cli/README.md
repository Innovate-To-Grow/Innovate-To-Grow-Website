# i2g-admin

A terminal CLI for remote record management of the Innovate-To-Grow backend.

It rides the **existing staff admin login**: `i2g-admin login` opens the browser to
the backend admin, you log in normally, and an OAuth2 **Authorization Code + PKCE**
exchange turns that completed login into a short-lived bearer token. The token is
cached in a `0600` file under `~/.config/i2g-admin/` and used for generic CRUD over
the backend's `/admin-api/` REST surface. No API keys, no long-term secrets.

## Install

```bash
cd cli && pip install -e .
```

## Usage

```bash
i2g-admin configure --base-url http://127.0.0.1:8000   # default: https://api.i2g.ucmerced.edu
i2g-admin login                                        # browser → admin login → token cached
i2g-admin whoami
i2g-admin models
i2g-admin schema event Event
i2g-admin records list projects Semester --filter year=2025 --order -year --limit 20
i2g-admin records get projects Semester <pk>
i2g-admin records create projects Semester --data '{"year": 2026, "season": 1}'
i2g-admin records update projects Semester <pk> --data @changes.json
i2g-admin records delete projects Semester <pk> --confirm-cascade
i2g-admin logout
```

- `--data` accepts inline JSON, `@file.json`, or `@-` to read JSON from stdin.
- `--json` prints machine-readable JSON; otherwise results render as Rich tables.
- The base URL can also be set with the `I2G_ADMIN_BASE_URL` environment variable.

Access requires the logged-in account be active **and** staff. There are no per-model
permission checks — staff status is the gate, backed by the backend's hard denylist.

## Develop

```bash
cd cli && pip install -e ".[test]"
pytest --cov=i2g_admin --cov-report=term-missing
```
