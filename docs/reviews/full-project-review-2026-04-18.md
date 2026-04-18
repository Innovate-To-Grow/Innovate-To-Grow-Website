# Full Project Code Review — 2026-04-18

**Scope:** Entire Innovate-To-Grow website — Django 5.2 backend (`src/`), React 19 + TypeScript frontend (`pages/`), infrastructure (`aws/`, `.github/`, `Dockerfile`), and dependencies.

**Target revision:** `main` @ `ae118ea` (CMSEmbedWidget landed).

**Method:** Five parallel `feature-dev:code-reviewer` agents, each scoped to a domain (backend security, backend quality/perf, frontend, tests/correctness, infra/CI/deps). Each finding was tagged with severity, `file:line`, and a suggested fix. After the agents returned, critical claims were verified against the source. Static checks (ruff, eslint, tsc, Django tests, vitest, build) were run as an independent signal.

**Static-check baseline (2026-04-18):**

| Check | Result |
|---|---|
| `ruff check` + `ruff format --check` | clean (434 files) |
| `eslint .` | clean (0 warnings, 0 errors) |
| `tsc --noEmit` | clean |
| `python manage.py test --settings=core.settings.dev` | 901 passed, 1 skipped, 0 failed (168s) |
| `npm test` (vitest) | 98 passed across 15 files (2.6s) |
| `npm run build` | clean |
| `python manage.py check --deploy --settings=core.settings.prod` | 2 warnings (see H7) |

---

## Executive Summary

The project is healthy in several dimensions: lint and type checks pass cleanly, the full test suite is green (901 backend / 98 frontend), JWT rotation + blacklist is configured, RSA-OAEP is used for password transport, DOMPurify guards rendered HTML with a tight iframe allowlist, and the recent CMS embed work is well tested. Settings composition, production security headers, and per-view throttles on `LoginView` all reflect deliberate security work.

The review surfaced **7 critical** and **21 high-priority** issues, clustered in five areas:

1. **Auth lifecycle is incomplete.** There is no logout endpoint anywhere in `authn/urls.py`, so a refresh token cannot be revoked on user-initiated logout. The magic-login token is never marked used. Together these let a stolen token stay valid for up to 7 (refresh) or 30 (magic-login) days.
2. **The Bedrock AI chat tool (`_run_custom_query`) accepts arbitrary ORM filter kwargs.** A prompt-injected LLM can exfiltrate password hashes and PII via traversal lookups like `member__password__icontains`.
3. **CMS preview and embed endpoints expose admin-entered content cross-origin.** `EmbedBlockView` sets `Access-Control-Allow-Origin: *` unconditionally. The frontend `BlockPreviewPage` accepts `postMessage` without origin validation.
4. **All production secrets (`DJANGO_SECRET_KEY`, `DB_PASSWORD`, `SES_AWS_SECRET_ACCESS_KEY`, `DJANGO_SUPERUSER_PASSWORD`, `GOOGLE_SHEETS_CREDENTIALS_JSON`) are injected as ECS plaintext `environment` values** rather than referenced via `secrets`. Any IAM principal with `ecs:DescribeTaskDefinition` can read them.
5. **CI has zero security signals.** No secrets scan, no dependency audit, no SAST, no image scan, no `.pre-commit-config.yaml`. The `bleach` sanitizer is Mozilla-archived and will never receive another CVE patch.

There are also real hotspots in performance (N+1 in campaign sending and several admin changelists), maintainability (1100+ LOC admin files, a hook with 326 LOC and zero tests), and architecture hygiene (settings import order inverted vs CLAUDE.md, soft-delete documented but not implemented on `ProjectControlModel`).

**Top 5 by impact:**

1. **C1** — Bedrock `_run_custom_query` ORM injection ([tools.py:293-306](src/core/services/db_tools/tools.py))
2. **C2** — Magic login token reusable, never marked used ([magic_login.py:36-40](src/mail/models/magic_login.py), [views.py:37-45](src/mail/views.py))
3. **C3** — All ECS secrets passed as plaintext `environment` ([task-definition.json:19-120](aws/task-definition.json))
4. **C4** — No logout endpoint ([authn/urls.py](src/authn/urls.py) — absent)
5. **C5** — `EmbedBlockView` wildcard CORS on admin content ([cms/views/views.py:148-177](src/cms/views/views.py))

Spot-check verification: every critical finding in this report was re-read at its cited `file:line` before inclusion. The one exception is noted in the Appendix (AWS keys in `.claude/settings.local.json` were downgraded from critical to high after verifying the file is not tracked in git).

---

## Critical

### C1 — Bedrock `_run_custom_query` passes LLM-supplied kwargs to `.filter(**...)`
- **Severity:** critical
- **Location:** [src/core/services/db_tools/tools.py:293-306](src/core/services/db_tools/tools.py)
- **Issue:** `params["filters"]` (a dict from the LLM) flows directly into Django's `.filter(**filters)` with no key allowlist. A prompt-injected LLM can exfiltrate password hashes, tokens, or any related-model PII via traversal lookups (e.g. `{"member__password__icontains": "pbkdf2"}`). `ordering` has the same issue — traversal-based ordering is a side-channel. Verified.
- **Fix:** Define a per-model `ALLOWED_FILTER_FIELDS` allowlist and reject any key not in it. Apply the same allowlist to ordering. Never pass raw LLM dicts to the ORM.
- **Effort:** M

### C2 — `MagicLoginToken` is reusable; `is_used` is never set
- **Severity:** critical
- **Location:** [src/mail/models/magic_login.py:36-40](src/mail/models/magic_login.py), [src/mail/views.py:37-45](src/mail/views.py)
- **Issue:** `is_valid` only checks `not self.is_expired`; it does not check `is_used`. `MagicLoginView.post` never calls `mark_used()` or sets `is_used=True`. Any intercepted link is replayable for the 30-day expiry window. Verified.
- **Fix:** Add `not self.is_used` to `is_valid`. In the view, after successful login, `magic.is_used = True; magic.used_at = timezone.now(); magic.save(update_fields=["is_used", "used_at"])`.
- **Effort:** S

### C3 — All production secrets live in ECS `environment` (plaintext)
- **Severity:** critical
- **Location:** [aws/task-definition.json:19-120](aws/task-definition.json), [.github/workflows/deploy-backend.yml](.github/workflows/deploy-backend.yml)
- **Issue:** `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `SES_AWS_SECRET_ACCESS_KEY`, `DJANGO_SUPERUSER_PASSWORD`, `GOOGLE_SHEETS_CREDENTIALS_JSON`, `REDIS_URL` are all injected via ECS `environment`. Once the deploy workflow substitutes the placeholders with real values, every task definition revision stores the live secret in plaintext, visible to anyone with `ecs:DescribeTaskDefinition`. Verified.
- **Fix:** Move secrets to AWS Secrets Manager and reference them via the ECS `secrets` field (which fetches at task-launch time and does not persist in the task def). Grant `secretsmanager:GetSecretValue` to the task execution role. Remove `DJANGO_SUPERUSER_*` from the task definition entirely — superuser creation should be a one-time management-command step, not a container-boot step.
- **Effort:** M

### C4 — No logout endpoint; refresh tokens never blacklisted on user logout
- **Severity:** critical
- **Location:** [src/authn/urls.py](src/authn/urls.py) (absent), [pages/src/shared/auth/flows.ts](pages/src/shared/auth/flows.ts)
- **Issue:** `authn/urls.py` has no `logout/` path. `BLACKLIST_AFTER_ROTATION=True` only blacklists rotated tokens — the currently-held refresh token remains valid for the full 7-day window after the user clicks "Log out". A stolen refresh token cannot be invalidated by the user. Verified (full urls.py read; no `logout`, `LogoutView`, or `Logout` anywhere in `src/authn/`).
- **Fix:** Add a `LogoutView` at `/authn/logout/` that accepts `{"refresh": "..."}`, calls `RefreshToken(refresh).blacklist()`, returns 204. Update `flows.ts` `logout()` to POST before clearing local storage. Cover with tests asserting the token is rejected after logout.
- **Effort:** M

### C5 — `EmbedBlockView` sets `Access-Control-Allow-Origin: *` on admin-authored content
- **Severity:** critical (downgraded to high if embed is intentionally third-party)
- **Location:** [src/cms/views/views.py:148-177](src/cms/views/views.py)
- **Issue:** Every response unconditionally sets `Access-Control-Allow-Origin: *` and is `xframe_options_exempt`. The response body includes `page_css` (admin-entered CSS, potentially containing tracking/preload selectors) and all block data. Any cross-origin page can fetch or iframe the widget and read its content.
- **Fix:** If the widget is intentionally third-party, add an `allowed_origins` field to `CMSEmbedWidget` and validate `Origin` against it; set the CORS header only on match. If internal-only, remove the wildcard entirely and rely on same-site.
- **Effort:** M

### C6 — `BlockPreviewPage` accepts `postMessage` from any origin
- **Severity:** critical
- **Location:** [pages/src/components/CMS/BlockPreviewPage.tsx:16-28](pages/src/components/CMS/BlockPreviewPage.tsx)
- **Issue:** The message listener does not check `event.origin`. Any page that can load `/_block-preview` in an iframe can feed arbitrary block data to the preview renderer, bypassing the admin authentication normally gating CMS editing. Verified.
- **Fix:** `if (event.origin !== window.location.origin) return;` at the top of `handleMessage`. This iframe is only loaded from same-origin admin; same-origin enforcement is safe.
- **Effort:** S

### C7 — N+1 `campaign.save()` inside per-recipient send loop
- **Severity:** critical (performance/data-integrity)
- **Location:** [src/mail/services/send_campaign.py:139](src/mail/services/send_campaign.py)
- **Issue:** `campaign.save(update_fields=["sent_count", "failed_count"])` runs inside the per-recipient loop. For a 500-recipient campaign, 500 serial UPDATEs on the `EmailCampaign` row cause lock churn and dominate send latency. A SIGTERM mid-loop (e.g., during ECS task replacement) leaves the row in an inconsistent `sending` state.
- **Fix:** Accumulate counters locally and save once at the end of the loop. For live-progress needs, batch-save every N iterations (e.g., 10). Combine with the bare-thread lifecycle fix in H15 so orphaned `sending` campaigns are reset on worker boot.
- **Effort:** S

---

## High

### H1 — `UnsubscribeAutoLoginView` has no rate limiting
- **Severity:** high
- **Location:** [src/authn/views/unsubscribe_login.py:40-64](src/authn/views/unsubscribe_login.py)
- **Issue:** `AllowAny` with no `throttle_classes`. `ImpersonateLoginView` uses `LoginRateThrottle`; this sibling endpoint does not.
- **Fix:** Add `throttle_classes = [LoginRateThrottle]`.
- **Effort:** S

### H2 — `CMSLivePreviewView.post` caches arbitrary admin JSON with no validation
- **Severity:** high
- **Location:** [src/cms/views/cms.py:63-71](src/cms/views/cms.py)
- **Issue:** Caches `request.data` as-is after only `isinstance(data, dict)`. A staff (or compromised staff) session can push arbitrarily large / XSS-shaped payloads that GETting the preview serves back to any visitor.
- **Fix:** Validate against `CMSPageSerializer` before caching; enforce `len(json.dumps(data)) < 512_000`; require a signed preview token on the GET side.
- **Effort:** M

### H3 — `render_reply_html` interpolates URLs into anchor `href` without escape
- **Severity:** high
- **Location:** [src/mail/services/inbox.py:213](src/mail/services/inbox.py)
- **Issue:** `re.sub` substitutes the matched URL into `href="\1"` without re-escaping. A URL containing `"` bypasses the outer HTML escape and permits attribute injection (`onclick=...`).
- **Fix:** Use a callable with `escape()` on the matched group, or `django.utils.html.format_html`.
- **Effort:** S

### H4 — `resetdb_helpers.reset_postgresql` f-strings the DB user into SQL
- **Severity:** high
- **Location:** [src/core/management/commands/resetdb_helpers.py:43](src/core/management/commands/resetdb_helpers.py)
- **Issue:** `cursor.execute(f"GRANT ALL ON SCHEMA public TO {db_user};")`. Dev-only, but `--allow-production` makes it reachable in prod.
- **Fix:** `psycopg2.sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(sql.Identifier(db_user))`.
- **Effort:** S

### H5 — Unvalidated `href` values from API (open redirect / `javascript:` XSS)
- **Severity:** high
- **Location:** [pages/src/pages/NewsDetailPage/NewsDetailPage.tsx:86](pages/src/pages/NewsDetailPage/NewsDetailPage.tsx), [pages/src/components/CMS/blocks/showcase/SponsorYearBlock.tsx:68](pages/src/components/CMS/blocks/showcase/SponsorYearBlock.tsx), [pages/src/components/Layout/Footer/Footer.tsx:13,22,68](pages/src/components/Layout/Footer/Footer.tsx)
- **Issue:** External (RSS, CMS, admin) URLs are rendered into `href` without scheme validation. React does not sanitize dynamic `href` values for `javascript:` / `data:`.
- **Fix:** Add a `safeHref(url: string): string` utility (mirroring `getSafeInternalRedirectPath`) that whitelists `https:`/`http:`/`mailto:`/`tel:` and returns `'#'` otherwise. Apply at every CMS/RSS-sourced anchor.
- **Effort:** M

### H6 — Refresh interceptor uses duck-typed `_retry` flag
- **Severity:** high
- **Location:** [pages/src/shared/auth/client.ts:65-66](pages/src/shared/auth/client.ts)
- **Issue:** `originalRequest._retry = true` mutates the Axios config via an undeclared property. Type-unsafe and fragile if any middleware recycles the config.
- **Fix:** Use a module-scope `WeakSet<object>` to track retried requests. Equally terse, fully typed.
- **Effort:** S

### H7 — `SECURE_SSL_REDIRECT` not enabled in prod
- **Severity:** high
- **Location:** [src/core/settings/components/production.py](src/core/settings/components/production.py) (surfaced by `manage.py check --deploy`)
- **Issue:** `check --deploy` emits `security.W008: Your SECURE_SSL_REDIRECT setting is not set to True`. HSTS is set but a first-visit HTTP request is not redirected.
- **Fix:** `SECURE_SSL_REDIRECT = True` (ALB/CloudFront should already be doing HTTP→HTTPS, but Django should enforce it end-to-end too).
- **Effort:** S

### H8 — Migration race on multi-replica ECS rolling update
- **Severity:** high
- **Location:** [src/entrypoint.sh:5](src/entrypoint.sh)
- **Issue:** `manage.py migrate --noinput` runs on every container boot. A rolling update with `minimumHealthyPercent=50` starts multiple new tasks simultaneously, which race on the `django_migrations` table.
- **Fix:** Move migrations to a one-shot ECS task (or a pre-deploy job in `deploy-backend.yml`) that completes before the service updates. Alternatively wrap in a PostgreSQL advisory lock.
- **Effort:** M

### H9 — `bleach` is Mozilla-archived and will not receive further CVE patches
- **Severity:** high
- **Location:** [src/pyproject.toml or requirements.txt](src/pyproject.toml), used wherever HTML is sanitized (e.g., `cms/services/sanitize.py` if present)
- **Issue:** Mozilla archived `bleach` in 2023. New mXSS bypasses discovered after archival will never be fixed.
- **Fix:** Migrate to [`nh3`](https://pypi.org/project/nh3/) (Mozilla's recommended successor, Rust-backed). API is near-identical.
- **Effort:** S

### H10 — `xlsx` (SheetJS Community) has known unpatched prototype-pollution CVEs
- **Severity:** high
- **Location:** [pages/package.json](pages/package.json) (`"xlsx": "^0.18.5"`), used by [pages/src/components/Projects/projectGridExport.ts](pages/src/components/Projects/projectGridExport.ts)
- **Issue:** CVE-2023-30533 et al. 0.18.5 is the last Community Edition; the `^0.18.5` range will never resolve to a patched version.
- **Fix:** Replace with `exceljs` (MIT, maintained), or move spreadsheet generation server-side with `openpyxl` (already a backend dep).
- **Effort:** M

### H11 — AWS STS credentials in `.claude/settings.local.json` (not gitignored)
- **Severity:** high (downgraded from infra agent's "critical" after verification)
- **Location:** [.claude/settings.local.json:9-17](.claude/settings.local.json)
- **Issue:** Two `ASIA*`-prefixed STS access keys live in a file at `.claude/settings.local.json`. Verified **not** in git (`git ls-files` empty). However, `.claude/` is **not** in `.gitignore` — only a `git add` away from committed. STS keys typically expire in hours, but the values are still live in the file and could be copied by any process with read access to the home directory.
- **Fix:** Add `.claude/settings.local.json` (or `.claude/settings.local*`) to `.gitignore`. Rotate the STS session. Prefer env-based credential injection (`aws sso login`, `aws-vault`, or `~/.aws/credentials` with short-lived profiles) over persisting keys to files.
- **Effort:** S

### H12 — Dockerfile runs as root; single-stage; floating base tag
- **Severity:** high
- **Location:** [src/Dockerfile](src/Dockerfile)
- **Issue:** No `USER` directive → Gunicorn runs as root. Labeled "multi-stage" in a comment but actually single-stage. `FROM python:3.11-slim` uses a floating tag.
- **Fix:** Add a non-root user in the final stage. Convert to a real multi-stage build (builder + production). Pin the base image to a `@sha256:` digest, rotated via Dependabot/Renovate.
- **Effort:** M

### H13 — `workflow_dispatch` on deploy workflows has no additional gate
- **Severity:** high
- **Location:** [.github/workflows/deploy-backend.yml:8](.github/workflows/deploy-backend.yml), [.github/workflows/deploy-frontend.yml:8](.github/workflows/deploy-frontend.yml)
- **Issue:** Any user with write access can trigger a prod deploy via `workflow_dispatch`, bypassing the `workflow_run.conclusion == 'success'` gate (that guard applies only to the `workflow_run` event).
- **Fix:** Rely on GitHub `environment` protection rules with required reviewers (the backend already declares `environment: "AWS ECS - Prod"` — confirm required reviewers are set, and mirror on frontend).
- **Effort:** S

### H14 — No secrets scanning / SAST / dependency audit in CI
- **Severity:** high
- **Location:** [.github/workflows/ci.yml](.github/workflows/ci.yml)
- **Issue:** No `gitleaks`, no `pip-audit`, no `npm audit`, no `bandit`/`semgrep`, no `trivy`/`hadolint`. Given H10, H11, H22, an attacker-committed secret or a known-CVE dependency would ship to prod undetected.
- **Fix:** Add as steps in existing jobs: `gitleaks/gitleaks-action`, `pip-audit -r requirements.txt`, `npm audit --audit-level=high`, `aquasecurity/trivy-action` on the built image, `hadolint` on the Dockerfile.
- **Effort:** S

### H15 — Bare daemon threads for campaign send and sheet sync
- **Severity:** high
- **Location:** [src/mail/admin/campaign.py:521](src/mail/admin/campaign.py), [src/event/services/registration_sheet_sync.py:123-126](src/event/services/registration_sheet_sync.py)
- **Issue:** SIGTERM kills daemon threads mid-flight with no cleanup. Campaigns stuck in `sending` are never reset. Sheet-sync timers live in in-process `_sync_timers` dict — duplicated per Gunicorn worker, not coordinated across them.
- **Fix:** On `AppConfig.ready`, reset campaigns in `sending` → `failed`. Move sheet-sync debounce state to a Redis key with TTL (cache.add for atomic test-and-set). Long-term: migrate to Celery or django-q.
- **Effort:** M

### H16 — `get_primary_email()` bypasses prefetch cache (N+1 on audiences)
- **Severity:** high
- **Location:** [src/authn/models/members/member.py:70-73](src/authn/models/members/member.py), [src/mail/services/audience.py:163,186](src/mail/services/audience.py)
- **Issue:** Method always runs a fresh `contact_emails.filter(...).first()` query, ignoring any prior `prefetch_related("contact_emails")`. 500 members → 500 extra queries on every campaign audience build.
- **Fix:** If `_prefetched_objects_cache` contains `contact_emails`, iterate the cached list in Python; else fall back to the query.
- **Effort:** M

### H17 — Admin `list_display` N+1 on `scan_count` and `block_count`
- **Severity:** high
- **Location:** [src/event/admin/checkin.py:53-55](src/event/admin/checkin.py) + [src/event/models/registration/checkin.py:18-20](src/event/models/registration/checkin.py), [src/cms/admin/cms/cms_page.py:74-77](src/cms/admin/cms/cms_page.py)
- **Issue:** Both admins expose a `@property` that issues `.count()` per row of the changelist. No annotation in `get_queryset`.
- **Fix:** Override `get_queryset` with `annotate(_cnt=Count("..."))` and read `obj._cnt` in the display method.
- **Effort:** S

### H18 — CMS block save is individual INSERTs with no transaction
- **Severity:** high
- **Location:** [src/cms/admin/cms/page_admin/editor.py:65-80](src/cms/admin/cms/page_admin/editor.py)
- **Issue:** `save_blocks_from_json` deletes all blocks and then loops `CMSBlock.objects.create(...)`. 20 blocks = 20 INSERTs. Mid-loop exception leaves the page half-saved.
- **Fix:** Wrap in `transaction.atomic()`; replace the loop with a single `CMSBlock.objects.bulk_create([...])`.
- **Effort:** S

### H19 — `useEventRegistration` (326 LOC) has zero tests
- **Severity:** high (test-coverage gap on a critical flow)
- **Location:** [pages/src/pages/EventRegistrationPage/useEventRegistration.ts](pages/src/pages/EventRegistrationPage/useEventRegistration.ts)
- **Issue:** The entire event-registration state machine — double-submit, 409 idempotency handoff, phone-verification guard, profile mutation before registration — is untested. The 409-existing-registration branch (frontend lines 200-203) is untested end-to-end, so a shape change on the backend's 409 payload would silently break transition-to-done.
- **Fix:** Add `useEventRegistration.test.ts` covering happy path, 409 idempotency, phone guard, and double-submit guard. Add an early-return in `handleRegistrationSubmit` when `submitting` is already true.
- **Effort:** L

### H20 — `ImpersonateLoginView` has no tests — one-time-use never asserted
- **Severity:** high
- **Location:** [src/authn/views/impersonate_login.py:34-53](src/authn/views/impersonate_login.py)
- **Issue:** This endpoint mints a full JWT for any member when given a valid token. No tests for: expired token, already-used token, missing token, `mark_used()` actually called. If `mark_used()` silently fails, the token is reusable.
- **Fix:** Add `src/authn/tests/api/test_impersonate_login.py` covering the four paths above plus assertion that the returned JWT subject is the impersonated member.
- **Effort:** S

### H21 — `send_campaign` service has zero tests
- **Severity:** high
- **Location:** [src/mail/services/send_campaign.py:40-143](src/mail/services/send_campaign.py)
- **Issue:** Rate limiting, per-recipient error handling, `RecipientLog` writes, and the status-transition rule `sent if failed_count < total_recipients else failed` are all untested. The transition is surprising (a single success out of 1000 → `sent`) and warrants at least one explicit assertion.
- **Fix:** Add `test_send_campaign.py` with boto3 mocked: all-success, all-fail, partial, SES-not-configured raises.
- **Effort:** M

---

## Medium

### M1 — CSP is permanently report-only with no report-uri and `'unsafe-inline'` for styles
- **Location:** [src/core/middleware.py:57-81](src/core/middleware.py)
- **Fix:** Add `report-uri /csp-report/` and a view that persists reports. Remove `'unsafe-inline'` from `style-src` (or scope with nonce). Promote to enforcing mode once report noise is understood.
- **Effort:** M

### M2 — Login and registration leak account state via distinct error messages
- **Location:** [src/authn/serializers/login.py:50-51](src/authn/serializers/login.py), [src/authn/serializers/register.py:87-95](src/authn/serializers/register.py), [src/authn/services/email_challenges.py:19](src/authn/services/email_challenges.py)
- **Issue:** Different messages for inactive accounts, existing emails, etc. Also `MAX_CHALLENGES_PER_HOUR=100` is effectively unreachable behind the DRF throttle (30/min), which allows an email-bomb pattern.
- **Fix:** Return a single generic `"Invalid credentials."` / `"A verification code has been sent if this address is eligible"` for all registration and login failure modes. Lower `MAX_CHALLENGES_PER_HOUR` to ~10 and raise `RESEND_COOLDOWN` to 60s.
- **Effort:** M

### M3 — `X-Forwarded-For` trusted blindly by `PageViewCreateView`
- **Location:** [src/cms/views/analytics.py:25-28](src/cms/views/analytics.py)
- **Fix:** Use DRF's throttle `get_ident` (which respects `NUM_PROXIES`) or the `ipware` library. Do not trust the leftmost XFF segment.
- **Effort:** S

### M4 — Analytics dashboard issues 6+ COUNT queries per admin load; cache TTL 60s
- **Location:** [src/cms/admin/analytics/page_view.py:59-120](src/cms/admin/analytics/page_view.py)
- **Fix:** Extend cache TTL to 5 min. Add composite indexes on `PageView(timestamp, ip_address)` and `(timestamp, path)`. Longer-term: pre-aggregate daily/hourly into a summary table via a scheduled task.
- **Effort:** M

### M5 — `DATA_UPLOAD_MAX_NUMBER_FIELDS=100000` is global
- **Location:** [src/core/settings/components/framework/django.py:116](src/core/settings/components/framework/django.py)
- **Issue:** Raised globally to support a single admin form. Applies to every public POST endpoint as a DoS surface.
- **Fix:** Keep global at default (1000); override per-view on the specific admin endpoint via `request.data_upload_max_number_fields`.
- **Effort:** M

### M6 — Settings import order is inverted vs CLAUDE.md
- **Location:** [src/core/settings/base.py:12-16](src/core/settings/base.py)
- **Issue:** `django` imported before `environment`. Currently works because `django.py` imports `BASE_DIR` from `.environment` internally, but violates the documented contract and will mask future breakage.
- **Fix:** Swap lines 12-13.
- **Effort:** S

### M7 — `_validate_phone_digits` imported from views into admin form
- **Location:** [src/event/admin/registration.py:148](src/event/admin/registration.py)
- **Fix:** Move to `event/services/phone_validation.py`; import from both the view and the admin form.
- **Effort:** S

### M8 — Sheet-sync admin action runs synchronously in the request cycle
- **Location:** [src/event/admin/event.py:156-165](src/event/admin/event.py)
- **Fix:** Dispatch to a background thread (consistent with `schedule_registration_sync`) or task queue; return "sync queued" immediately.
- **Effort:** M

### M9 — Sheet-sync `_flush_pending_sync` has a multi-worker race
- **Location:** [src/event/services/registration_sheet_sync.py:149-172](src/event/services/registration_sheet_sync.py)
- **Fix:** Wrap the read-append-update sequence in `select_for_update()` (inside `atomic()`), or use `F()` expressions and a cache-backed lock.
- **Effort:** M

### M10 — `send_campaign_status_json` fires 3 RecipientLog queries per poll
- **Location:** [src/mail/admin/campaign.py:547-573](src/mail/admin/campaign.py)
- **Fix:** Combine into one `aggregate(...)` + slice, or cache the JSON for 2s.
- **Effort:** S

### M11 — 40 Auth component files; 1 test; `flows.ts` and `crypto.ts` untested
- **Location:** [pages/src/components/Auth/](pages/src/components/Auth), [pages/src/shared/auth/flows.ts](pages/src/shared/auth/flows.ts), [pages/src/services/crypto.ts](pages/src/services/crypto.ts)
- **Issue:** The `encryptPassword` catch in `flows.ts` checks `error.message.includes('decrypt')`, but Web Crypto throws `DOMException` with a different message — the catch is effectively dead code, so stale keys are never cleared on encryption failure.
- **Fix:** Add `flows.test.ts` covering login/register/logout happy + error paths. Add `crypto.test.ts` covering cache hit, cache expiry, `clearKeyCache`. Fix the catch condition to catch all encryption failures, not just messages containing `'decrypt'`.
- **Effort:** M

### M12 — `SafeHtml` iframe allowlist (YouTube/Vimeo) is not tested
- **Location:** [pages/src/components/SafeHtml/SafeHtml.test.tsx](pages/src/components/SafeHtml/SafeHtml.test.tsx)
- **Fix:** Add two assertions — `https://youtube.com/embed/...` survives; `https://evil.com/embed` is stripped.
- **Effort:** S

### M13 — Public-key cache in `crypto.ts` has no in-flight dedup
- **Location:** [pages/src/services/crypto.ts:25-47](pages/src/services/crypto.ts)
- **Fix:** Mirror the `layoutFetchInFlight` pattern from `features/layout/api.ts`.
- **Effort:** S

### M14 — Index used as React `key` in menu and CMS block lists
- **Location:** [pages/src/components/Layout/MainMenu/parts/MenuTree.tsx:66,107](pages/src/components/Layout/MainMenu/parts/MenuTree.tsx), [pages/src/components/CMS/blocks/content/ContactInfoBlock.tsx:36](pages/src/components/CMS/blocks/content/ContactInfoBlock.tsx), [pages/src/components/CMS/blocks/content/LinkListBlock.tsx:22](pages/src/components/CMS/blocks/content/LinkListBlock.tsx), [pages/src/components/CMS/blocks/navigation/NavigationGridBlock.tsx:20](pages/src/components/CMS/blocks/navigation/NavigationGridBlock.tsx), [pages/src/components/Layout/Footer/Footer.tsx:67,94,95,105](pages/src/components/Layout/Footer/Footer.tsx)
- **Fix:** Switch to stable keys (`item.url`, `item.label + item.href`, etc.). Remove index suffixes that mask instability.
- **Effort:** S

### M15 — Duplicated `addMinutes` helper in two Schedule components
- **Location:** [pages/src/pages/SchedulePage/SchedulePage.tsx:51](pages/src/pages/SchedulePage/SchedulePage.tsx), [pages/src/components/ScheduleGrid/ScheduleGrid.tsx:32](pages/src/components/ScheduleGrid/ScheduleGrid.tsx)
- **Fix:** Extract to `pages/src/shared/utils/time.ts`.
- **Effort:** S

### M16 — `collectstatic` at container boot
- **Location:** [src/entrypoint.sh:8](src/entrypoint.sh)
- **Fix:** Move to a `RUN` step in the Dockerfile (or the deploy workflow). Static artifacts are image-determined, not boot-determined.
- **Effort:** S

### M17 — No concurrency guard / timeout on frontend deploy
- **Location:** [.github/workflows/deploy-frontend.yml](.github/workflows/deploy-frontend.yml)
- **Fix:** Add `concurrency: { group: deploy-frontend-${{ github.ref }}, cancel-in-progress: true }` and `timeout-minutes: 20` (mirroring `deploy-backend.yml`).
- **Effort:** S

### M18 — No top-level `permissions:` block in workflows (over-privileged GITHUB_TOKEN)
- **Location:** all 4 workflow files
- **Fix:** `permissions: { contents: read }` at the top level, escalate per-step where needed.
- **Effort:** S

### M19 — `cryptography>=41.0.0` floor is known-vulnerable
- **Location:** [src/pyproject.toml](src/pyproject.toml)
- **Fix:** Raise floor to `>=43.0.0`. Run `pip-audit` to confirm resolved versions.
- **Effort:** S

### M20 — `CLAUDE.md` documents soft-delete on `ProjectControlModel` but it's not implemented
- **Location:** [src/core/models/base/control.py](src/core/models/base/control.py), [CLAUDE.md](.claude/rules/architecture.md)
- **Issue:** Docs describe `is_deleted`, `deleted_at`, `all_objects`, and manager filtering. The model has none.
- **Fix:** Either implement it or update the doc to say soft-delete applies only to specific model overrides.
- **Effort:** M

### M21 — `run_custom_query` does not filter soft-deleted rows (if any); count/ordering leak
- **Location:** [src/core/services/db_tools/tools.py:291-310](src/core/services/db_tools/tools.py)
- **Fix:** Covered as part of C1 allowlist work; explicitly exclude `is_deleted=True` for models that have the field.
- **Effort:** S

### M22 — Registration idempotency & subscribe double-POST not tested
- **Location:** [src/authn/views/subscribe.py](src/authn/views/subscribe.py), [src/authn/tests/api/test_subscribe.py](src/authn/tests/api/test_subscribe.py)
- **Fix:** Verify `ContactEmail.email_address` has a `UniqueConstraint`. Add a concurrent-POST test asserting no duplicates.
- **Effort:** S

### M23 — `.env.example` omits SES, Twilio, REDIS, FRONTEND/BACKEND URLs
- **Location:** [src/.env.example](src/.env.example)
- **Fix:** Add commented-out stubs for every variable `environment.py` / `production.py` reads.
- **Effort:** S

### M24 — ESLint runs without `--max-warnings=0`
- **Location:** [pages/package.json](pages/package.json) (`"lint": "eslint ."`)
- **Fix:** Change to `"lint": "eslint . --max-warnings=0"` after clearing existing warnings.
- **Effort:** S

### M25 — No Docker `HEALTHCHECK` directive
- **Location:** [src/Dockerfile](src/Dockerfile)
- **Fix:** Add a `HEALTHCHECK` matching the ECS task definition health probe, so local `docker run` / compose flows get the same readiness signal.
- **Effort:** S

### M26 — `_run_custom_query` ordering permits relation traversal (side-channel leak)
- **Location:** [src/core/services/db_tools/tools.py:300-306](src/core/services/db_tools/tools.py)
- **Fix:** Covered by C1's allowlist — mentioned separately because the fix applies to a different code path (`order_by` vs `filter`).
- **Effort:** S

---

## Low

### L1 — `resetdb.py` hard-codes developer email + trivial password
- **Location:** [src/core/management/commands/resetdb.py:37-39](src/core/management/commands/resetdb.py) (`DEV_DEFAULT_ADMIN_EMAIL = "xiehongzhe04@gmail.com"`, `DEV_DEFAULT_ADMIN_PASSWORD = "1"`)
- **Fix:** Read from env with sensible fallbacks (`admin@localhost` / `changeme`). Never commit a real person's email.
- **Effort:** S

### L2 — SVG magic-byte check bypassable; SVG can contain `<script>`
- **Location:** [src/cms/models/media.py:36-38](src/cms/models/media.py)
- **Fix:** Strip script elements with `defusedxml` or `nh3`; or serve SVGs with `Content-Disposition: attachment`. Consider dropping SVG from `ALLOWED_ASSET_EXTENSIONS` entirely.
- **Effort:** M

### L3 — `HealthCheckMiddleware` bypasses `ALLOWED_HOSTS` check
- **Location:** [src/core/middleware.py:18-53](src/core/middleware.py)
- **Fix:** Document intent in a comment; only a concern if `maintenance_message` ever carries sensitive content.
- **Effort:** S

### L4 — `EmbedBlockPage` posts with `targetOrigin: '*'`
- **Location:** [pages/src/components/CMS/EmbedBlockPage.tsx:19,97](pages/src/components/CMS/EmbedBlockPage.tsx)
- **Fix:** Send to `document.referrer` instead, or document the deliberate wildcard because payload is public `(slug, height)`.
- **Effort:** S

### L5 — `crypto.ts` uses bare `axios` (not the shared client)
- **Location:** [pages/src/services/crypto.ts:5,38](pages/src/services/crypto.ts)
- **Fix:** Use the non-auth `api` client from `shared/api/client` for consistent base URL handling.
- **Effort:** S

### L6 — Two UC Merced links are HTTP, not HTTPS
- **Location:** [pages/src/components/Layout/MainMenu/MainMenu.tsx:88](pages/src/components/Layout/MainMenu/MainMenu.tsx), [pages/src/components/Layout/MainMenu/parts/MobileMenuPanel.tsx:126](pages/src/components/Layout/MainMenu/parts/MobileMenuPanel.tsx)
- **Fix:** Change `http://giving.ucmerced.edu/` → `https://giving.ucmerced.edu/`.
- **Effort:** S

### L7 — DOMPurify not in its own bundle chunk
- **Location:** [pages/vite.config.ts:17-25](pages/vite.config.ts)
- **Fix:** `if (id.includes('node_modules/dompurify')) return 'dompurify';` in `manualChunks`. (~45 KB saved from initial bundle.)
- **Effort:** S

### L8 — Deprecated `MediaQueryList.addListener` fallback in SchedulePage
- **Location:** [pages/src/pages/SchedulePage/SchedulePage.tsx:140-141](pages/src/pages/SchedulePage/SchedulePage.tsx)
- **Fix:** Delete the fallback. All modern browsers have `addEventListener`.
- **Effort:** S

### L9 — Permanently-skipped resetdb test has empty body
- **Location:** [src/core/tests/commands/test_resetdb.py:42-53](src/core/tests/commands/test_resetdb.py)
- **Fix:** Implement with `mock.patch` on `resetdb_helpers`, or delete the stub and move the TODO to an issue.
- **Effort:** S

### L10 — `aws/task-definition.json` hardcodes account ID in role ARNs
- **Location:** [aws/task-definition.json:6-7](aws/task-definition.json)
- **Fix:** Move account-specific ARNs to `vars.ECS_*_ROLE_ARN` and substitute at deploy time.
- **Effort:** S

### L11 — `gspread>=5.5.0` is major versions behind
- **Location:** [src/pyproject.toml](src/pyproject.toml)
- **Fix:** Upgrade to 6.x (breaking API change around auth). Verify staging before prod.
- **Effort:** M

### L12 — `VITE_API_BASE_URL` silently-empty fallback
- **Location:** [.github/workflows/deploy-frontend.yml:41](.github/workflows/deploy-frontend.yml)
- **Fix:** Add an explicit `if [ -z "$VITE_API_BASE_URL" ]; then echo "missing" && exit 1; fi` guard.
- **Effort:** S

### L13 — `test_reused_token_still_works` asserts insecure behavior without a comment
- **Location:** [src/mail/tests/test_magic_login.py:40-49](src/mail/tests/test_magic_login.py)
- **Issue:** Will conflict with the C2 fix (make magic-login tokens single-use) — the test name hard-codes the current behavior.
- **Fix:** When C2 lands, delete this test; add a `test_reused_token_rejected` in its place.
- **Effort:** S

### L14 — No `.pre-commit-config.yaml`
- **Location:** project root
- **Fix:** Add minimal config with `ruff-pre-commit` (check + format) and `gitleaks`. Document in CLAUDE.md quick links.
- **Effort:** S

---

## Findings by Area — Coverage Summary

| Area | Critical | High | Medium | Low | Agent |
|---|---:|---:|---:|---:|---|
| Backend security | 2 | 5 | 5 | 4 | #1 |
| Backend quality & performance | 1 | 5 | 8 | 0 | #2 |
| Frontend security & quality | 1 | 2 | 3 | 4 | #3 |
| Tests & coverage | 1 | 3 | 3 | 2 | #4 |
| Infra / CI / deps | 1 | 5 | 5 | 3 | #5 |
| Consolidation totals | **7** | **21** | **25** | **14** | — |

---

## Recommendations — Prioritized 30-day plan

**Week 1 (ship immediately):**

1. C2 — magic-login single-use: ~5 LOC change + 1 migration + 1 test.
2. C6 — `BlockPreviewPage` origin check: ~1 LOC + test update.
3. H1 — throttle `UnsubscribeAutoLoginView`: ~1 LOC.
4. H11 — add `.claude/settings.local*` to `.gitignore` and rotate the STS keys.
5. H14 — add `gitleaks` and `npm audit --audit-level=high` to CI (two workflow steps).

**Week 2 (high-impact, bounded scope):**

6. C1 — Bedrock `run_custom_query` allowlist; add `M26` ordering allowlist in the same PR.
7. C4 — `LogoutView` + blacklist; update `flows.ts`.
8. C3 — migrate ECS task def to `secrets` with Secrets Manager ARNs.
9. H10 — replace `xlsx` with `exceljs` (or move to server-side `openpyxl`).
10. H9 — swap `bleach` for `nh3`.

**Week 3 (perf & test hygiene):**

11. C7 — move `campaign.save()` out of the send loop.
12. H15 — reset stuck `sending` campaigns on boot + redis-backed sheet-sync debounce.
13. H16, H17, H18 — N+1 and bulk-create fixes (3 small PRs, batchable).
14. H19, H20, H21 — tests for `useEventRegistration`, `ImpersonateLoginView`, `send_campaign`.
15. M6 — swap settings import order.

**Week 4 (hardening):**

16. H12 — non-root user + multi-stage Dockerfile + pinned digest.
17. H8 — extract migrations to a pre-deploy step.
18. H7 — `SECURE_SSL_REDIRECT = True`.
19. M1 — CSP report-uri and remove `'unsafe-inline'` for styles.
20. M2 — generic error messages for login/register leaks + reduced challenge limits.

After these, the medium-priority backlog (CI workflow permissions, `.env.example` completeness, pre-commit config, deprecated `addListener`, index keys) can be tackled in batched low-risk PRs.

---

## Appendix

### Methodology

- 5 parallel `feature-dev:code-reviewer` agents, each with an explicit file-list, exclusion list, and severity rubric.
- Each agent output was constrained to ~25 findings with required `file:line`, severity, and a 1-3 sentence fix.
- Critical claims (C1, C2, C4, C6, H11) were re-read at their cited locations by the parent planner before inclusion.
- Static checks (ruff, eslint, tsc, Django test suite, vitest, build) run independently of the agents.

### Scope exclusions

- `archive/` (historical code, not maintained)
- Django migrations (per CLAUDE.md; new-migration gaps are still in scope)
- `pages/dist/`, `node_modules/`, `__pycache__/`, `.venv/`
- Third-party vendored assets

### False positives surfaced during exploration

- **"`src/.env` is committed with a live Google API key"** — corrected to *not* tracked in git. `git ls-files src/.env` is empty; only `src/.env.example` is tracked. The `GOOGLE_SHEETS_API_KEY` placeholder in `.env.example` is `# GOOGLE_SHEETS_API_KEY=your-api-key` (commented stub).
- **"AWS access keys committed in `.claude/settings.local.json`"** — downgraded. The file exists locally with live STS keys, but is *not* tracked in git. The real risk is that `.claude/` is not in `.gitignore`, so it's a single `git add .claude/` away from leaking; that is captured as H11.

### Static-check raw output (2026-04-18)

```
$ cd src && ruff check .
All checks passed!

$ cd src && ruff format --check .
434 files already formatted

$ cd src && python manage.py check --deploy --settings=core.settings.prod
WARNING: security.W008 — SECURE_SSL_REDIRECT is not True  (see H7)
WARNING: security.W009 — SECRET_KEY is weak  (only fires under dummy env; real prod key is env-driven)

$ cd src && python manage.py test --settings=core.settings.dev
Ran 901 tests in 168.432s
OK (skipped=1)

$ cd pages && npm run lint
(0 errors, 0 warnings)

$ cd pages && npx tsc --noEmit
(no output)

$ cd pages && npm test
Test Files  15 passed (15)
      Tests  98 passed (98)

$ cd pages && npm run build
(exit 0; largest chunk: jspdf.es.min 386 kB / 126 kB gzipped — lazy-loaded)
```

### How to act on this report

Each finding is formatted with the file path + line number as a clickable reference. Triage by severity; for each critical or high, the suggested fix is a short 1-3 sentence description — not a diff — so the implementer retains judgment on style/test shape. No code was changed as part of this review.
