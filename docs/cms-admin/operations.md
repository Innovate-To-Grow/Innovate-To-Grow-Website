# Operations

Maintenance tasks, data management, and operational guidance for administrators.

## Maintenance mode

### Enabling

The `SiteMaintenanceControl` model (`src/apps/core/models/base/web.py`) controls maintenance mode:

1. In Django admin → Site Settings → Site Maintenance Control
2. Set `is_maintenance = True`
3. Optionally set a custom `message` and `bypass_password`
4. Save

### Behavior

- The `/health/` endpoint returns `{"maintenance": true}` in its response
- The frontend `HealthCheckProvider` detects this and shows the maintenance overlay
- The bypass password allows specific users to access the site during maintenance via `/maintenance/bypass/`

### Disabling

Set `is_maintenance = False` in the admin. The frontend polls every 10 seconds and will automatically recover.

## Database management

### Development reset

```bash
cd src && python manage.py resetdb --force
```

**Warning:** Destroys all data. Creates a fresh database with migrations applied and seeds a default admin user. Has safety guards — refuses to run against PostgreSQL in production-like settings.

### Migrations

```bash
cd src && python manage.py makemigrations    # Generate
cd src && python manage.py migrate           # Apply
```

**Critical rule:** Never edit a migration that has been merged to `main`. Create a new migration instead. The CI pipeline validates migrations against PostgreSQL to catch issues SQLite won't surface.

#### Event date-range rollout cleanup

Migration `event.0008_event_date_range_and_registration_status` uses an expand/contract rollout because ECS tasks run migrations while the previous task revision may still be serving traffic. Django removes `is_live` immediately, but its physical database column is temporarily retained with a `false` database default. `end_date` is required and range-validated by the new application state and forms, but existing values remain `NULL`, the physical column remains nullable, and the physical date-range constraint is deferred so an old task can finish an insert or move its single Event date safely.

After the new revision is fully deployed and every old task has drained, add a follow-up migration that backfills `end_date IS NULL` rows from `date`, materializes the `event_end_date_gte_start_date` check constraint, makes `end_date` physically `NOT NULL`, and drops the physical `is_live` column. Normalize invalid phone settings again before the contract step as a defensive check. Do not combine that contract step into the first rolling deployment.

## Service configuration

### Seeding skeleton configs

```bash
cd src && python manage.py seed_service_configs
```

Creates an empty active `EmailServiceConfig` row for backend defaults. AWS credentials, region, End User Messaging origination number, and SMS OTP template are entered through the AWS Credentials admin UI, not via `.env`. `AWSCredentialConfig` is also created when `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are set locally.

### Verifying configs before deploy

```bash
cd src && python manage.py verify_service_configs --strict
```

Confirms an active `EmailServiceConfig` and AWS credentials are configured for SES. Add `--require-sms`, `--require-google`, or `--require-aws` to harden the check before removing env vars or rotating secrets.

### Managing via admin

Configuration models are available in Django admin:

| Model | Admin area | Purpose |
|-------|------------|---------|
| `AWSCredentialConfig` | Site Settings | Shared AWS IAM key, region, SMS origination number, and OTP template for SES, SMS, and Bedrock |
| `EmailServiceConfig` | Site Settings | Sender identity and campaign send rate |
| `GoogleCredentialConfig` | Site Settings | Google service-account JSON |
| `GmailAccessAccount` | Site Settings | Gmail IMAP import account |
| `MemberSheetSyncConfig` | Members & Auth | Member-to-Sheets selection |
| `CurrentProjectSchedule` | Events | Published current-project schedule/source |
| `PastProjectsSheetConfig` | Projects | Past-project Sheets source |
| `SystemIntelligenceConfig` | System Intelligence | Bedrock and public-assistant behavior |
| `SiteMaintenanceControl` | Site Settings | Maintenance mode toggle |

The selector models permit only one active/enabled row in their scope; saving a replacement demotes the previous row. `SiteMaintenanceControl` is a separate true singleton stored at primary key `1`.

### Active configuration recovery

Active selection is fail-closed. Runtime `load()` methods never fall back to an inactive row:

- AWS, email, Google, Gmail, system-intelligence, current-schedule, and past-project selectors permit at most one active row.
- Member Sheet Sync permits at most one enabled row.
- RSA permits at most one active row per key name.
- AWS, Google, and Gmail loaders return an unsaved, unconfigured default; Email returns unsaved sender defaults; Member Sheet Sync returns an unsaved disabled default; System Intelligence returns unsaved defaults; schedule/project loaders return `None`.
- An unexpected duplicate raises instead of letting `.load()` choose a row. The database constraints should make that state impossible after the invariant migrations.

Check active-row counts without printing credentials:

```bash
cd src
python manage.py shell -c "from apps.core.models import AWSCredentialConfig as A, EmailServiceConfig as E, GoogleCredentialConfig as G, GmailAccessAccount as M; print({'aws': A.objects.filter(is_active=True).count(), 'email': E.objects.filter(is_active=True).count(), 'google': G.objects.filter(is_active=True).count(), 'gmail': M.objects.filter(is_active=True).count()})"
python manage.py shell -c "from apps.authn.models import MemberSheetSyncConfig as M, RSAKeypair as R; print({'member_sync': M.objects.filter(is_enabled=True).count(), 'auth_rsa': R.objects.filter(name='auth-encryption', is_active=True).count()})"
python manage.py shell -c "from apps.event.models import CurrentProjectSchedule as E; from apps.projects.models import PastProjectsSheetConfig as P; from apps.system_intelligence.models import SystemIntelligenceConfig as S; print({'schedule': E.objects.filter(is_active=True).count(), 'past_projects': P.objects.filter(is_active=True).count(), 'system_intelligence': S.objects.filter(is_active=True).count()})"
```

Every value must be `0` or `1`. A required service showing `0` is an explicit outage/configuration state, not permission to use an old row. In Django admin, inspect the inactive records, select the intended row, mark it active/enabled, and save normally; model save logic deactivates the previous row transactionally. Do not use bulk SQL to bypass model logic.

Then verify the services required by this environment:

```bash
python manage.py verify_service_configs --strict --require-aws --require-sms --require-google
```

If an invariant migration kept the wrong deterministic winner, reactivate the intended row through the admin after the migration finishes. Do not fake or reverse the constraint migration as a configuration-recovery technique.

## Authentication incident and handoff runbook

### Migration verification

The current security/configuration rollout must preserve these app-local dependency chains:

| App | Ordering |
|-----|----------|
| `authn` | `0015` → `0016` → `0017_auth_security_invariants` |
| `core` | `0027_backgroundjob` → `0028_active_config_invariants` → `0029_deliveryratelimit` |
| `event` | `0009_registration_sheet_sync_audit` → `0010_active_schedule_invariant` |
| `projects` | `0008_pastprojectshare_version` → `0009_active_sheet_config_invariant` |
| `system_intelligence` | `0005_active_config_invariant` → `0006_public_assistant_input_limits` |

Inspect the graph and plan first:

```bash
cd src
python manage.py showmigrations authn core event projects system_intelligence
python manage.py migrate --plan
```

For PostgreSQL, run the migration through the advisory-lock command:

```bash
python manage.py migrate_locked --noinput --lock-timeout-seconds 600
python manage.py migrate_locked --check --lock-timeout-seconds 60
```

`migrate_locked` refuses non-PostgreSQL databases. It waits up to the configured timeout for the repository-specific session advisory lock and exits without migrating if it cannot acquire it.

### Session/bootstrap failures

`GET /authn/session/` is the authoritative authenticated profile bootstrap. Expected triage:

| Result | Meaning | Recovery |
|--------|---------|----------|
| `200` | JWT is valid; response contains current profile state and next step | Do not replace it with stale browser profile data |
| First `401`, then `200` | Access token expired and the client refreshed successfully | Expected |
| Repeated `401` | Refresh is missing, rejected, blacklisted, or belongs to an obsolete local generation | Sign in again; do not copy tokens between accounts/tabs |
| `5xx` | Backend/database/profile serialization failure | Check application logs and database readiness; a client retry must not overwrite a newer session generation |

The endpoint itself never issues tokens. Token rotation remains the responsibility of `/authn/refresh/`.

### SMS challenge failures

SMS request endpoints need an explicitly active, configured AWS record to send. Verification of a code that was already sent uses only `PhoneVerificationChallenge`; it does not make an AWS call.

Inspect recent challenge metadata without displaying phone numbers or code hashes:

```bash
python manage.py shell -c "from apps.authn.models import PhoneVerificationChallenge as C; print(list(C.objects.order_by('-created_at').values('id', 'purpose', 'status', 'attempts', 'max_attempts', 'expires_at', 'consumed_at')[:20]))"
```

The supported purposes are `phone_auth`, `contact_phone_verify`,
`password_reset`, `password_change`, and `event_registration`. A successful
verification changes exactly one matching row from `pending` to `consumed`.
Wrong attempts persist; five attempts or expiry changes the row to `expired`.
A new request for the same phone and purpose/context expires the prior pending
row before creating another.

When verification fails:

1. Confirm the caller returned the `challenge_id` from the matching request and did not mix purposes or browser tabs.
2. Check status, expiry, and attempt count. Do not reset a used/expired row or try to recover the hashed OTP.
3. Issue a new request and use its new ID. Phone-only lookup is a one-release compatibility path, not an operator recovery mechanism.
4. If requesting the replacement returns `503`, run `verify_service_configs --strict --require-aws --require-sms` and repair the active AWS config.

Password-reset request responses always contain a `challenge_id`; email and unknown identifiers receive a decoy UUID to preserve the enumeration-safe response shape. Do not infer account existence from that field.

### RSA encryption failures

List auth key metadata without exposing private key material:

```bash
python manage.py shell -c "from apps.authn.models import RSAKeypair as R; print(list(R.objects.filter(name='auth-encryption').order_by('-created_at').values('key_id', 'is_active', 'created_at', 'rotated_at')))"
```

Exactly one row should be active. It rotates after one day into a new row;
retired rows remain decryptable for 24 hours, remain stored until 48 hours, and
are then purged opportunistically. An unknown or expired `key_id`
intentionally fails closed.

- For an isolated stale-key error, have the client discard its cached key, fetch `/authn/public-key/`, and encrypt the password again. Never retry the old ciphertext against the current key.
- If no active row exists, requesting `/authn/public-key/` creates one. The equivalent controlled recovery command is:

  ```bash
  python manage.py shell -c "from apps.authn.services.rsa_manager import get_or_create_auth_keypair; key = get_or_create_auth_keypair(); print({'key_id': str(key.key_id), 'created': key.created_at.isoformat()})"
  ```

- If private-key decryption began failing after `DJANGO_SECRET_KEY` changed,
  confirm the secret change first. Restore the prior secret when continuity is
  required, or deliberately regenerate the active `auth-encryption` key in
  Django admin and require clients to refetch. Do not reactivate a retired key;
  preserve it through the 48-hour retention window.

### One-time credential replay

- Email login/registration codes, password/deletion verification tokens, and SMS challenges use locked or conditional state transitions. One concurrent caller succeeds; later callers receive an invalid/expired response.
- Impersonation links expire after five minutes and are conditionally marked used before JWT issuance. An already-used result is expected replay protection; issue a fresh link instead of changing `is_used`.
- Failed email/SMS attempts and expiry transitions are deliberately committed before error responses. Do not treat a rising attempt counter as a transaction bug.

### Handoff acceptance checklist

- [ ] `showmigrations` marks the five invariant migrations applied and `migrate_locked --check` exits successfully on PostgreSQL.
- [ ] `python manage.py check` and `python manage.py makemigrations --check --dry-run` pass.
- [ ] The public-key endpoint returns one current `auth-encryption` key ID; an authenticated session request returns the current profile/next-step state.
- [ ] Every SMS consumer persists and returns `challenge_id`, including phone auth, contact verification, password change, and phone password reset.
- [ ] The active-row count commands show no value above `1`, and required services pass `verify_service_configs --strict` with the appropriate requirement flags.
- [ ] Operators know that SMS verification survives a post-send AWS outage,
  retired RSA keys decrypt for 24 hours and remain stored for 48, and replayed
  codes/tokens must not be reset for reuse.
- [ ] Before removing phone-number-only verification, tests and observed traffic confirm no supported client still uses the compatibility path.

## News sync

```bash
cd src && python manage.py sync_news --settings=config.settings.local
```

Fetches articles from all configured `NewsFeedSource` records. Results logged in `NewsSyncLog`.

For production, this should be run on a schedule (cron or scheduled task).

## Route redirect operations

Create exact legacy-path mappings in **Content Management System → Route Redirects**. Confirm that the destination is already public, save the inactive record, review the conflict result, and then activate it. Do not create redirect records through migrations or fixtures for one-off business URLs.

An active record takes effect in the SPA immediately. The admin separately reports the Amplify edge state:

- **Synced** — the corresponding HTTP 301 rules have been reconciled ahead of the SPA fallback.
- **Pending** — the database change is live in the SPA but the background worker or Amplify configuration has not completed edge publication.
- **Failed** — inspect the sanitized error, correct IAM/configuration, and use **Retry edge sync**.

Edge publication requires the durable-job worker to run continuously with the
same database and environment configuration as the Web service. Production and
demo run it as the no-port `itg-background-worker` sidecar:

```bash
python manage.py run_background_worker --settings=config.settings.production
```

The sidecar overrides the Docker entrypoint and waits for the Web container to
be healthy, so it does not race the Web startup migration or run Uvicorn. Deploy
the schema and sidecar first with `BACKGROUND_JOBS_ENABLED=false`, confirm the
`worker` CloudWatch stream is polling, then set the flag to true and redeploy so
saved redirects begin queueing reconciliation work. On that enabled startup,
the worker also queues one immediate full Amplify reconciliation to bootstrap
or repair the environment's canonical edge rules. If active
mappings were saved while jobs or Amplify configuration were unavailable,
select them in Admin and run **Retry edge sync** after enabling the worker.

The backend reconciler is the sole repository-managed `UpdateApp` writer. It
owns the canonical sitemap, API, optional admin/static/media proxy, CMS 301,
and final SPA fallback rules while preserving unrelated rules already on the
app. The frontend deployment publishes the build but does not read or replace
the Amplify custom-rule list. Backend deploys stamp both Web and worker with the
numeric `AMPLIFY_CONFIG_REVISION=<run_id>.<run_attempt>` generation; the deploy
workflow owns this value, so operators should not override it manually.

After deployment, create and verify these initial mappings manually in Admin;
they are intentionally not included in a migration, fixture, or seed script:

| Source | Destination |
|--------|-------------|
| `/I2G-project-sponsor-acknowledgement` | `/sponsor-acknowledgement` |
| `/I2G-student-agreement` | `/student-agreement` |
| `/FAQs` | `/faqs` |

For each mapping, confirm the destination returns 200 before activation, then
verify both source variants (with and without a trailing slash), an original
query string, and the final browser URL. Once edge status is **Synced**, also
verify the source response itself is HTTP 301.

Production and demo each require their own `AMPLIFY_APP_ID`. For this feature,
add only `amplify:GetApp` and `amplify:UpdateApp` to each ECS task role, scoped
to that environment's matching `arn:aws:amplify:<region>:<account>:apps/<app-id>`
resource. Route records are disabled rather than deleted so reconciliation can
identify and remove edge rules it previously owned.

For retirement of `innovatetogrow.ucmerced.edu`, coordinate DNS and TLS with OIT, inventory legacy paths first, then configure an HTTP/HTTPS whole-domain 301 to `https://i2g.ucmerced.edu` that preserves path and query. Test the old host, the same path on the canonical host, and any CMS path remap as separate redirect hops.

## Event operations

### Opening and closing registration

Public registration is controlled per event by the **Registration open** checkbox in Event admin, and multiple events can accept registrations at once. Event date ranges include both the start and end dates. Schedule/current-project publication is configured separately through `CurrentProjectSchedule`.

### Registration sheet sync

From Event admin:
- **Automatic**: The registration transaction creates a durable Sheets job;
  the worker serializes by event and appends only missing `Registration ID`
  values
- **Full replace**: Admin action backs up a populated legacy/drifted tab,
  replaces it from PostgreSQL, and protects the final ID column

### Schedule import

From Event admin:
- Triggers schedule sync from Google Sheets
- Creates/updates `Semester`, `Project`, and schedule models

### Check-in

- Staff-only barcode scanning via `POST /event/check-in/scan/`
- Barcode format: `I2G|EVENT|{event_slug}|{ticket_code}`
- Check-in status dashboard: `GET /event/check-in/status/`

## Project import

Projects are imported via CSV in the Semester admin page. The CSV service (`src/apps/projects/services/`) maps columns to `Project` model fields.

## Member operations

### Superuser creation

```bash
cd src && python manage.py createsuperuser
# Prompts for email (not username)

# Non-interactive:
cd src && python manage.py createsuperuser --email admin@example.com
```

### Member import/export

Available through the Member admin:
- Import from Excel (openpyxl)
- Export to Excel

## Monitoring

### Health check

`GET /health/` returns:
```json
{"status": "ok", "database": "ok", "maintenance": false, "maintenance_message": ""}
```

Use `/livez/` for container liveness and `/readyz/` for database-backed readiness monitoring.

### Sync logs

| Log model | Location in admin | Tracks |
|-----------|------------------|--------|
| `RegistrationSheetSyncLog` | Events section | Google Sheets sync success/failure |
| `NewsSyncLog` | CMS section | RSS feed sync results |
| `RecipientLog` | Mail section (inline) | Email delivery per recipient |

### Application logs

- **Local**: Console output from `python manage.py runserver`
- **Production**: CloudWatch at `/ecs/itg-backend` (us-west-2)

## Related pages

- [Django Admin](django-admin.md) — Admin interface navigation
- [Content Management](content-management.md) — CMS publishing workflow
- [API: Auth & Mail](../api/auth-and-mail.md) — Session, challenge, key, and one-time credential contracts
- [Local Development](../deployment/local-development.md) — Migration graph and authentication smoke checks
- [Google Sheets: Operations](../integrations/google-sheets/operations.md) — Sheets-specific troubleshooting
- [Deployment: Environments](../deployment/environments.md) — Environment configuration
