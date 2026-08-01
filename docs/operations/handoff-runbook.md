# Production Handoff Runbook

This is the operating guide for the crew responsible for Innovate To Grow after
the remediation rollout. PostgreSQL is authoritative for application state and
the durable job queue. Redis is required for the public-assistant budget
reservation path. Production releases promote immutable artifacts built by CI.

## First-day access and ownership checklist

Confirm named owners and backup owners for:

- GitHub repository administration, protected environments, and break-glass
  approvals
- AWS IAM/OIDC, ECS, ECR, RDS, ElastiCache, S3, Amplify, CloudWatch, SES, and
  SNS
- Google Cloud service accounts and every registration, schedule, member, and
  past-project spreadsheet
- Django administrators and service-configuration records
- DNS, TLS, incident communications, and the operational alert destination

Do not copy secret values into this document, tickets, chat, or deployment
logs. Record only the secret manager path and the team that owns rotation.

## Runtime map

| Component | Durable dependency | Health or evidence |
|---|---|---|
| Django web service | PostgreSQL, Redis, S3, configured providers | `/livez/`, `/readyz/`, `/health/` |
| Background worker | PostgreSQL; SES/SNS/Sheets as used by a job | CloudWatch `WorkerHeartbeat` and worker logs |
| React frontend | Immutable Amplify artifact and Django API | Semantic deployment smoke test |
| Archive service | Google Sheets API | `/healthz`, `/readyz`, semantic proxy smoke test |
| Public assistant | Bedrock and shared Redis | API status, reservation/spend metrics, Redis health |

Supported development and build versions are Python 3.11.x, Node.js 22.22 or
newer on the 22 line, and npm 10 or newer. Production Python dependencies come
from the hashed lock in `src/requirements/production.lock.txt`.

## Normal deployment

Normal production workflows are push-triggered and promote the exact full
commit SHA that passed CI. They do not rebuild the application during deploy.

1. Require a green aggregate `CI Result` on `main`.
2. Confirm the published backend/archive image digests and frontend artifact
   were produced by that same run.
3. Let the backend workflow run `migrate_locked` in a one-off ECS task.
4. Confirm the migration task exits successfully before the worker or web
   service changes.
5. For the first durable-job rollout, deploy the worker with
   `BACKGROUND_WORKER_ENABLED=true` and `BACKGROUND_JOBS_ENABLED=false`.
6. Confirm the workflow observes a fresh target-specific worker heartbeat.
7. Enable `BACKGROUND_JOBS_ENABLED=true` while leaving the worker flag true,
   then confirm web readiness, job drainage, semantic smoke tests, and the
   deployed SHA/digest.

Never run migrations or `collectstatic` from a normal web/worker container
startup. Never update an existing demo administrator through bootstrap;
`ensure_default_admin` is create-only.

The complete environment and IAM setup is in the
[production deployment configuration](../deployment/production.md).

## Background-worker health

The initial production topology is one ECS worker running:

```bash
python manage.py run_background_worker
```

The worker emits a JSON metric snapshot each cycle and, when
`BACKGROUND_JOB_METRICS_NAMESPACE` is set, publishes:

| Metric | Healthy interpretation |
|---|---|
| `WorkerHeartbeat` | Recent samples are present while the service should be running |
| `QueueDepth` | Returns toward zero after traffic spikes |
| `OldestJobAge` | Remains below the agreed delivery/sync SLO |
| `FailedJobs` | No unexplained increase |
| `UncertainJobs` | Zero, or every item has an assigned reconciliation owner |

Triage a missing heartbeat in this order:

1. Check ECS desired/running task counts and recent deployment events.
2. Inspect worker logs for settings, database, provider, or claim-cycle errors.
3. Verify `/readyz/` on the matching web revision and PostgreSQL connectivity.
4. Confirm the worker task has the same immutable backend image and required
   production settings as the web task.
5. Run one bounded diagnostic cycle in an authorized task:

   ```bash
   python manage.py run_background_worker --once
   ```

Do not enable queueing until the schema is deployed and a worker heartbeat has
been observed. The deployment workflow enforces this sequence: it can deploy
the worker independently with `BACKGROUND_WORKER_ENABLED=true`, verifies the
exact ECS task definition, and waits for a fresh CloudWatch heartbeat before
updating web. It rejects `BACKGROUND_JOBS_ENABLED=true` when the worker flag is
false. Production and demo must use distinct metrics namespaces.

Before disabling the worker, first deploy
`BACKGROUND_JOBS_ENABLED=false` with the worker flag still true. Drain or
explicitly account for queued jobs, scale the worker service to zero, and then
set `BACKGROUND_WORKER_ENABLED=false`; the disabled workflow does not scale an
existing worker automatically.

### Failed and uncertain jobs

Use Django admin → Core → Background Jobs. Payloads, errors, attempts, claim
times, and provider-call markers are read-only. The only mutation is the
explicit **Retry selected failed/uncertain jobs** action.

- `failed` means the attempt was definitively rejected or exhausted safe
  retries. Correct the cause before retrying.
- `uncertain` means an external provider call may have succeeded. The worker
  deliberately will not resend it automatically.

For an uncertain email or SMS, reconcile the recipient, provider event/message
history, campaign log, timestamp, and destination first. Record the evidence
and approver in the incident/change record. Retry only if the operator accepts
the duplicate-delivery risk. A worker crash before a provider call remains
safe to retry; a crash after the call begins is quarantined.

## Registration Sheets reconciliation

Every managed registration sheet must have the exact event-specific header,
with the non-editable `Registration ID` column last. That UUID is the
idempotency key. Append jobs serialize on the event row, select a bounded
cutoff snapshot, read existing IDs, append only missing registrations, and
advance the cursor only after a confirmed write.

Before moving a legacy or drifted sheet to append mode:

1. Confirm the service account has Editor permission.
2. Export or otherwise independently back up the sheet.
3. In Django admin, select one canary event and run **Sync registrations to
   sheet**.
4. The application also duplicates a populated legacy/drifted tab before its
   full replacement. Confirm that backup exists.
5. Verify the final `Registration ID` column is protected and contains one
   UUID per registration row.
6. Compare database count, unique sheet IDs, and visible row count at the
   recorded cutoff.
7. Review `RegistrationSheetSyncLog`: `cursor_from`, `cursor_to`, selected IDs,
   `rows_written`, status, and sanitized failure detail.
8. Enable/continue append jobs for the canary, create a test registration, and
   confirm exactly one new ID appears.
9. Repeat for the remaining events only after the canary reconciles.

If a sync fails, do not edit the cursor. Fix credentials, permissions, GID, or
header drift, then rerun. Append mode intentionally refuses a populated legacy
sheet or a changed header until a backed-up full sync establishes the managed
schema. The authoritative recovery action is a full sync from PostgreSQL, not
manual reconstruction from partial sheet rows.

## Active-configuration shutdown and recovery

The database enforces at most one active configuration for AWS, email, Google,
Gmail, system intelligence, current schedule, past-project sheet, member
sheet sync, and each RSA key name. Loaders fail closed when no active row
exists; they do not reactivate or reuse an inactive record.

Before a release or after a configuration change:

```bash
python manage.py verify_service_configs --strict
```

Add provider-specific requirements such as `--require-google` where the
deployment depends on them. Deactivate the sole active row only for an
intentional service shutdown, with an incident/change record and a tested
recovery path. Expected consequences include rejected SMS sends, halted Sheets
jobs, disabled AI invocation, or unavailable mail—not fallback to old
credentials.

If a config-backed service stops:

1. Check the active-row count and `is_configured` state in Django admin.
2. Check the related worker job and sanitized error.
3. Restore or create one valid active row; do not edit migration history or
   bypass the uniqueness constraint.
4. Re-run strict verification and one bounded provider smoke test.
5. Manually retry only the jobs proven safe to repeat.

## Authentication RSA key rotation

Password-transport RSA rotation creates a new `RSAKeypair` row and key ID; it
does not overwrite the old row. Retired private keys:

- remain eligible to decrypt ciphertext addressed to their key ID for 24 hours
- remain stored for incident/debug overlap until 48 hours after retirement
- are deleted after the 48-hour retention boundary

The normal auth service rotates the active `auth-encryption` key when due. For
an incident, use the protected Django admin action to regenerate/rotate, then:

1. Confirm exactly one active `auth-encryption` row.
2. Confirm `/authn/public-key/` returns the new `key_id`.
3. Test a freshly encrypted login.
4. Keep the prior row available through the stated windows.
5. Verify expired old ciphertext fails closed and stale rows are purged.

Never reactivate an old private key merely to make a stale client request pass.
The client must fetch the current public key and encrypt again.

## CSP observation and promotion

Both the Django response policy and Amplify policy begin in report-only mode.
Keep report-only mode for at least seven representative days before enforcing.

1. Set and validate `AMPLIFY_CSP_FRAME_SOURCES` from the active CMS embed-host
   allowlist. Only HTTPS origins/wildcards are accepted.
2. Monitor sanitized, rate-limited reports received at `/csp-report/`.
3. Group violations by directive, route, browser, blocked origin, and release.
4. Fix application-owned inline code or missing exact origins. Do not add broad
   schemes, `unsafe-inline`, or `unsafe-eval` to silence reports. Unfold 0.91
   ships the CSP-compatible Alpine runtime; the project also disables HTMX
   expression evaluation, swapped script tags, and injected indicator styles
   through the bundled `htmx-csp-config.js` bootstrap. The admin action
   bootstrap also gives Material Web/Lit the per-response nonce for its
   fallback style elements. Material Web imports are pinned to one immutable
   jsDelivr package version; the analytics Chart.js assets are also pinned and
   protected with Subresource Integrity.
   `style-src-attr 'unsafe-inline'` remains as an attribute-only compatibility
   rule for Django Admin, Unfold, CodeMirror, and the QR widget. It does not
   permit inline `<style>` elements, inline scripts, or event handlers.
5. Verify CMS preview messages require `window.parent` plus the per-preview
   nonce, and that public iframe sanitization uses the published embed-host
   revision.
6. After seven clean days, set backend `CSP_REPORT_ONLY=false` and Amplify
   `AMPLIFY_CSP_MODE=enforce`, deploy, and verify the enforcing
   `Content-Security-Policy` header. Confirm that Django's policy contains the
   exact `STATIC_URL`/`MEDIA_URL` origin and Google Fonts origins, and that all
   source-owned inline admin scripts/styles carry the response nonce.

If enforcement breaks a critical route, restore report-only mode through an
immutable deployment and capture the violation. Do not hot-edit the deployed
artifact.

## Break-glass deployment and rollback

Use **Break-glass Production Deploy** only when the normal path cannot meet the
incident need. It requires:

- a component
- a full immutable 40-character SHA reachable from `main`
- a successful CI run for that SHA
- a mandatory incident/change reason
- approval from the protected `Production Break Glass` environment

For rollback, choose the last known-good immutable SHA/digest and promote it
through break-glass. Do not force-push `main`, rebuild an old source checkout,
or roll back an expand/contract schema with destructive reverse migrations.
Keep new nullable columns/tables compatible until the later contract release.
Manifest-hashed static objects are retained through the rollback window, so a
prior application revision can still load its assets.

After rollback, verify database compatibility, web readiness, worker
heartbeat, semantic frontend/archive smoke tests, queue state, and the recorded
deployed SHA/digest.

## Dependency refresh

Python locks are generated with the pinned `pip-tools` version in
`src/requirements/lock-tools.txt`. Update inputs, regenerate both Python 3.11
locks, review the complete diff, and run the lock verifier. Do not hand-edit
hashes or suppress an advisory.

```bash
cd src
./scripts/compile-requirements.sh
./scripts/check-requirements-locks.sh
python -m pip install --require-hashes -r requirements/local.lock.txt
python -m pip_audit -r requirements/production.lock.txt

cd ../pages
npm ci
npm audit --audit-level=moderate
```

Use the archive equivalents in `archive/page/`. Update the CLI lock/build
metadata through its documented `uv`/wheel workflow. Dependabot covers
frontend, backend, CLI, archive, Docker, and GitHub Actions.

## Release verification commands

Run the repository’s complete CI workflow for the canonical gate. The local
equivalents below are useful before pushing:

```bash
# Backend
cd src
../.venv/bin/ruff check .
../.venv/bin/ruff format --check .
../.venv/bin/python manage.py check
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py test --settings=config.settings.local
./scripts/check-requirements-locks.sh

# Frontend
cd ../pages
npm ci
npm run lint
npx tsc --noEmit
npm test -- --run
npm run build
npm audit --audit-level=moderate

# Standalone CLI
cd ../cli
uv run ruff check .
uv run pytest
uv run bandit -r src
uv run pip-audit
uv build

# Archive
cd ../archive/page
python -m pytest
./check-requirements-locks.sh

# Workflow contracts
cd ../..
python -m unittest discover -s .github/scripts/tests -p 'test_*.py'
actionlint
```

CI additionally runs PostgreSQL concurrency tests, coverage, CodeQL, Semgrep,
Trivy, Bandit, dependency audits, Docker builds/scans, Playwright local/live
projects, immutable-artifact checks, and semantic deployment smoke tests.
High/Critical fixable findings fail the release unless a validated,
owner/rationale/expiry exception exists.

## Incident quick triage

| Symptom | First checks | Do not do |
|---|---|---|
| Authentication lockouts or refresh failures | challenge attempts/expiry, session endpoint, token generation, cross-tab race logs | reset consumed challenges for reuse |
| Sheet lag or missing rows | worker heartbeat, event job, sync log cutoff/IDs, sheet header/protection | advance the cursor manually |
| Campaign stuck or partial | recipient logs, queue age, failed/uncertain jobs, SES/SNS provider evidence | bulk retry uncertain deliveries |
| Assistant 503 | Redis health, reservation/spend counters, Bedrock status | bypass the shared reservation limit |
| Archive 502/not ready | allowlisted Sheets request, credentials, timeout logs | cache an upstream failure as healthy |
| CSP breakage | enforcing/report-only headers and sanitized reports | add a broad unsafe source |
| Deployment mismatch | workflow SHA, ECR digest, ECS task definition, Amplify artifact | rebuild or retag `latest` |

For every production incident, preserve timestamps, release SHA/digest, job
IDs, provider IDs, sanitized logs, actions, approvers, and final reconciliation.

## Production rollout items that remain manual

Repository code cannot perform these governance or observation steps:

- configure GitHub protected environments and required reviewers
- provision/restrict GitHub OIDC IAM roles and remove long-lived AWS keys
- enable ECR tag immutability and confirm rollback retention
- provision the ECS worker service, alarms, dashboards, target-specific
  metrics namespace, task-role `cloudwatch:PutMetricData`, and deploy-role
  `cloudwatch:GetMetricStatistics`
- set the production Redis secret and provider/service configuration rows
- back up and canary each existing registration sheet
- observe CSP report-only traffic for seven real days before enforcement
- execute staged deploys and verify real production telemetry

The handoff is complete only when those items have an owner, target date,
evidence link, and rollback decision.
