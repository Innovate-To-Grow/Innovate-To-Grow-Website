# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Run the app (development)
```bash
python app.py          # Waitress server on 0.0.0.0:5001 with 8 threads
python app.py --debug  # Flask debug mode on 0.0.0.0:5001
```

### Run tests
```bash
pytest tests/                              # all tests
pytest tests/logic/test_registration_logic.py  # single test file
pytest tests/logic/test_registration_logic.py::test_name -v  # single test
```
Tests require the Google Sheets service account to be configured and will only run against the "Test I2G Membership" spreadsheet (enforced by `conftest.py` safety check). No linter or formatter is configured. New tests should go in `tests/logic/`; the `tests/legacy/` directory contains older integration tests.

### Install dependencies
```bash
pip install -r requirements.txt
```

## Architecture

This is a **Flask** membership and event management system for the Innovate To Grow (I2G) organization at UC Merced.

### Data storage is split between two backends
- **Google Sheets** (via gspread): Primary data store for Members, Prospects, and Logs worksheets. Accessed through the global `wks`, `prospects`, and `logs` objects exported from `project/__init__.py`.
- **SQLite** (via SQLAlchemy): Stores admin users, dynamic form field definitions (`edit_form`), and event configurations (`event`). DB at `project/db/data.sqlite3`. No migration system — tables are created via `db.create_all()` on first run.

### Key application globals (project/__init__.py)
The `__init__.py` file exports many shared objects used across the app: `app`, `db`, `ses`, `sqs`, `sh` (spreadsheet handle), `wks`, `prospects`, `logs`, `cache`, `limiter`, `tz`. Import these from `project` when needed. Also exports `get_wks_records(wks)` and `get_wks_columns(wks)` helpers for reading sheet data.

### Blueprint routing structure
All membership routes are prefixed with `/membership` (configured via `Config.URL_PREFIX`):
- **home** — public-facing pages (cached with `@cache.cached()`)
- **registration** (`/membership/signup`) — multi-step signup with email/phone verification
- **update** — member info updates with token-based email links
- **events** (`/membership/events`) — event registration with dynamic form fields
- **confirm** (`/membership/otp`) — OTP phone verification flow
- **geo** — geolocation utilities

### Separation of concerns in business logic
- `project/views/` — Flask route handlers (HTTP layer only)
- `project/utils/*_utils.py` — Pure business logic functions (testable, no side effects). These return dataclass decision objects (e.g., `CompleteRegistrationDecision`) that describe what actions to take.
- `project/utils/side_effect_helpers.py` — Functions that write to Google Sheets, send emails, etc. Consumes decision objects from the utils layer.
- `project/forms/` — WTForms form definitions, including custom validators (`NotEqualTo`, `MultiCheckboxAtLeastOne`, `ConditionalRequiredIfFieldProvided`)
- `project/utils/dynamic_fields.py` — Generates WTForms fields at runtime from `edit_form` DB records
- `project/services/logging_service.py` — Google Sheets logging

### Async patterns
- Background threads (`Thread.start()`) for email sending and logging to avoid blocking requests
- `asyncio.gather()` used for parallel Google Sheets column queries within registration logic
- `@copy_current_request_context` decorator preserves Flask context in background threads

### External service integrations
- **AWS SES** — transactional email sending (via boto3 `ses` client)
- **AWS SQS** — message queuing (via boto3 `sqs` client)
- **Twilio** — SMS OTP phone verification (`project/utils/twilio.py`)
- **Google Maps API** — geolocation
- **Gmail IMAP** — bounce detection (via imap-tools)
- **itsdangerous** — token generation for email verification links (time-limited, signed with SECRET_KEY + SECURITY_PASSWORD_SALT)

### Rate limiting and caching
- Flask-Limiter: 15 requests per 30 seconds (admin routes exempt)
- Flask-Caching: 300s default timeout, simple in-memory cache

### Configuration
- `config/default.py` — all config values loaded from environment (`.env` file via python-dotenv)
- `.env` — secrets (not committed)
- `service_account.json` — Google Sheets service account credentials (not committed, must be at project root)

### Admin panel
Flask-Admin at `/admin` with custom views for user management, form builder, events, contacts, manual emails, bounce detection, documentation, and prospects management. Protected by Flask-Login. Default admin created on first run: `admin@admin.com` / `admin`.
