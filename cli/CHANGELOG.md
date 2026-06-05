# Changelog

All notable changes to the `i2g-admin` CLI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-04

This release reshapes the CLI toward AWS-CLI-style ergonomics. It refactors the
package into a runtime/commands/formatters layout and lands the foundation for a
broader command surface. Some capabilities are wired into the option surface and
delivered incrementally; until each lands, the corresponding path fails fast with
a clear "not available in this build yet" message rather than silently no-op'ing.

### Added

- **Named profiles** — keep several environments side by side. `config.json` holds
  per-profile settings (`base_url`) and the active `default_profile`; the `default`
  profile reuses the legacy `credentials.json`, while named profiles use
  `credentials-<name>.json` (all `0600`). Select with `--profile <name>` or
  `I2G_ADMIN_PROFILE`. Profile names are restricted to `[A-Za-z0-9._-]`.
- **`configure get/set/list`** — AWS-style configuration subcommands, in addition
  to the back-compat bare `configure` and `configure --base-url <url>`.
- **Global options on the root** (placed *before* the command, AWS-style):
  `--profile`, `--output`, `--query`, `--no-paginate`, `--max-items`, `--page-size`,
  `--max-attempts`, `--connect-timeout`, `--read-timeout`, `--debug`, `--version`.
- **`--output table|json`** output pipeline, with `--json` as a per-command alias
  for `--output json`. `text`/`yaml`/`csv` formats are registered as recognized
  choices (filled in a later release).
- **Per-request timeouts** — `--connect-timeout` / `--read-timeout` (defaults 5s / 30s).
- **`--debug`** — emit the error `repr` on failures.

### Changed

- **No baked-in backend URL.** The base URL resolves from the active profile's
  stored `base_url`, then the legacy `credentials.json`, then `I2G_ADMIN_BASE_URL`
  (env or `cli/.env`). A missing value is a clear configuration error — there is no
  hardcoded production default.
- **Package layout** carved into extension seams: a Typer root in `app.py`, one
  module per command group under `commands/`, shared glue in a leaf `runtime.py`
  (command modules import `runtime`, not `app`, to avoid an import cycle), a
  per-invocation `Context`, and pluggable `--output` / `--query` pipelines.

### Roadmap (wired, delivered incrementally)

- `--query` JMESPath projection and `--output text|yaml|csv` formats.
- Auto-pagination (`--no-paginate` / `--max-items` / `--page-size`) and HTTP
  retry/backoff (`--max-attempts`).
- New commands: `apps`, `records count`, `records wait --until field=value`,
  `completion show <shell>` (plus Typer's `--install-completion`/`--show-completion`).
- `records create/update --generate-cli-skeleton` / `--cli-input-json`.
- Richer `schema` output (verbose name, help text, default, choices-with-labels, FK target).

## [0.1.0]

### Added

- Initial release: OAuth2 Authorization Code + PKCE login that rides the existing
  staff admin login, a cached `0600` bearer token, and generic record CRUD over
  `/admin-api/` (`login`, `logout`, `whoami`, `models`, `schema`,
  `records list/get/create/update/delete`, `configure`).
