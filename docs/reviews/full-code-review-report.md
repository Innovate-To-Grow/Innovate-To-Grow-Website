# Full Code Review Report

## 1. Executive Summary

The repository is in generally workable shape: the backend is modular, the frontend structure is understandable, and the automated backend test surface is much stronger than average for a project of this size. The codebase also shows clear intent around separation of apps, admin workflows, and public API boundaries.

The main risks are concentrated in trust boundaries and deployment/runtime hardening rather than basic structure. The highest-priority issues are an anonymous CMS live-preview path that can expose unpublished content, an event registration flow that trusts a client-supplied `phone_verified` flag, profile-damaging behavior in the authenticated subscribe flow, and production secret handling that still relies on plain ECS environment variables.

Overall recommendation: keep the current architecture, but treat the security and runtime-hardening findings below as release-blocking for production-facing work. After those are addressed, invest in stronger frontend behavior tests and production-faithful CI coverage.

## 2. Review Scope and Method

Reviewed areas:

- Backend Django/DRF code under `src/`
- Frontend React/TypeScript/Vite code under `pages/`
- Active documentation under `docs/`
- Historical material under `archive/`
- CI/CD and deployment files under `.github/` and `aws/`
- Top-level project configuration including `README.md`, `pyproject.toml`, and `pages/package.json`

Signals used:

- Static review of code, settings, URLs, serializers, views, services, models, admin code, tests, and workflows
- Cross-checking frontend/backend contracts in API usage and route/data flow
- Local test execution:
  - `python manage.py test --settings=core.settings.dev` from `src/` -> `695` tests passed, `1` skipped
  - `npm test` from `pages/` -> `55` tests passed

Limitations and uncertainty:

- This was primarily a code/config review plus local automated test execution; no live AWS deployment, browser walkthrough, or load/security scanning was performed.
- Some XSS-related risk depends on whether upstream editors or content sources sanitize HTML before it reaches the reviewed code. No central sanitization layer was visible in the reviewed repository.
- `archive/` was reviewed only as historical material because `archive/README.md` explicitly marks it as non-runtime content.

## 3. Findings

No critical findings were confirmed.

### [High] Anonymous CMS Live Preview Can Expose Unpublished Content
- Confidence: High
- Area: backend
- Files:
  - `src/cms/views/cms.py:39-53`
  - `src/cms/tests/cms/test_cms_views.py:195-199`
- Problem:
  `CMSLivePreviewView` allows anonymous `GET` requests and, on cache miss, falls back to loading a page directly from the database by UUID without checking publication status or staff access.
- Why it matters:
  Anyone with a page UUID can retrieve draft or otherwise unpublished CMS content. That is materially weaker than the published-only behavior in `CMSPageView` and defeats preview isolation.
- Evidence:
  `get_permissions()` returns `AllowAny` for non-`POST` requests. `get()` first checks cache, then returns `CMSPageSerializer(page).data` for any matching page. Existing tests explicitly assert the anonymous DB fallback behavior.
- Recommendation:
  Remove the DB fallback for anonymous access, or require a signed preview token or staff authentication before serving uncached live-preview data.
- Suggested tests:
  Anonymous `GET` for a draft page should return `403` or `404`.
  Authenticated staff or signed-preview access should continue to work.
  Published-page behavior should be explicitly defined and covered.

### [High] Event Registration Trusts a Client-Supplied `phone_verified` Flag
- Confidence: High
- Area: backend
- Files:
  - `src/event/serializers/registration.py:20-22`
  - `src/event/views/registration.py:124-159`
- Problem:
  The registration API accepts `phone_verified` from the client and persists it without validating any server-side proof that the phone challenge was actually completed.
- Why it matters:
  An authenticated client can mark an arbitrary submitted phone number as verified, which undermines the integrity of event phone verification and contaminates synced account contact data.
- Evidence:
  The serializer exposes `phone_verified`. In `EventRegistrationCreateView`, `create_kwargs["phone_verified"] = True` is set purely from request data, then that state is propagated into `sync_phone_to_account(..., verified=phone_verified_inline)`.
- Recommendation:
  Replace the boolean with a server-issued verification artifact tied to the verified number and validate that artifact during registration creation.
- Suggested tests:
  Registration with `phone_verified=true` but no verification artifact should fail.
  A valid artifact for the same phone number should succeed.
  A mismatched phone/artifact pair should fail.

### [High] Authenticated Subscribe Flow Can Overwrite Existing Profile Data With Blanks
- Confidence: High
- Area: frontend
- Files:
  - `pages/src/pages/SubscribePage/SubscribePage.tsx:30-35`
  - `pages/src/pages/SubscribePage/SubscribePage.tsx:74-89`
  - `pages/src/shared/auth/profile.ts:10-18`
  - `src/authn/views/account/profile.py:91-96`
  - `src/authn/serializers/profile.py:90-97`
- Problem:
  When an already-authenticated user lands on `/subscribe`, the page skips straight to the profile step but does not preload the existing profile. Submitting the form sends blank strings for any untouched fields.
- Why it matters:
  A user trying to opt into email updates can accidentally erase stored profile fields such as `middle_name`, `last_name`, or `organization`.
- Evidence:
  Local state initializes these profile fields to empty strings. `handleProfileSubmit()` always sends those fields in `updateProfileFields()`. The backend PATCH path applies any provided field values directly.
- Recommendation:
  Hydrate the form from `getProfile()` before showing the step, or submit only changed fields instead of always sending blank defaults.
- Suggested tests:
  Authenticated subscribe flow should preserve existing profile fields when the user only enables subscription.
  Explicitly cleared fields should still be supported when the user intentionally removes them.

### [High] Backend Deployment Injects Sensitive Values as Plain ECS Environment Variables
- Confidence: High
- Area: infra
- Files:
  - `aws/task-definition.json:19-115`
  - `.github/workflows/deploy-backend.yml:84-193`
- Problem:
  Database credentials, SES secrets, Django superuser credentials, and Google Sheets credentials are rendered into the ECS task definition as normal `environment` entries rather than ECS `secrets` references.
- Why it matters:
  Those values become part of the task-definition payload and are readable to anyone with access to ECS task definitions or related deployment artifacts.
- Evidence:
  The task-definition template stores placeholders under `environment`, and the workflow replaces them inline before deployment.
- Recommendation:
  Move sensitive values to AWS Secrets Manager or SSM Parameter Store and wire them into ECS using the `secrets` field rather than plain environment variables.
- Suggested tests:
  Add a deployment-template validation step that fails if sensitive variable names are present under `environment` instead of `secrets`.
  Add an integration check that renders the task definition and asserts secrets are referenced, not embedded.

### [Medium] Email and Ticket Tokens Have Overly Permissive Replay and Expiry Behavior
- Confidence: High
- Area: backend
- Files:
  - `src/event/services/ticket_assets.py:19-47`
  - `src/event/views/ticket_login.py:20-30`
  - `src/authn/services/unsubscribe_token.py:15-25`
  - `src/authn/views/unsubscribe_login.py:24-34`
  - `src/mail/models/magic_login.py:14-42`
- Problem:
  Ticket-login and unsubscribe-login links are reusable until expiry, and ticket access tokens have no expiry at all.
- Why it matters:
  If an email link or ticket token leaks through mailbox forwarding, browser history, logs, or screenshots, it can be replayed for repeated JWT issuance or long-lived ticket access.
- Evidence:
  Ticket and unsubscribe tokens use `signing.dumps/loads` without one-time consumption tracking. `get_registration_from_access_token()` validates signature only and does not pass `max_age`. In contrast, `MagicLoginToken` is explicitly one-time-use.
- Recommendation:
  Use one-time DB-backed tokens for login-style links and apply bounded lifetimes plus revocation or rotation for ticket access tokens.
- Suggested tests:
  Second use of a ticket-login or unsubscribe token should fail.
  Expired ticket access tokens should be rejected.
  Resent or rotated ticket links should invalidate prior tokens.

### [Medium] Maintenance Bypass Secret Is Stored and Compared in Plaintext
- Confidence: High
- Area: backend
- Files:
  - `src/core/models/base/web.py:24-30`
  - `src/core/views.py:43-58`
  - `src/core/admin/maintenance.py:9-10`
- Problem:
  The maintenance bypass password is stored in plaintext in the database and compared with direct string equality.
- Why it matters:
  Anyone with database or admin read access can recover the bypass secret directly, and the comparison path does not benefit from Django's standard password-hashing behavior.
- Evidence:
  `bypass_password` is a plain `CharField`; `MaintenanceBypassView` compares `password == config.bypass_password`; the admin exposes the field directly.
- Recommendation:
  Store a password hash using Django password hashers, validate with `check_password`, and mask the field in admin.
- Suggested tests:
  Saving a bypass password should hash it.
  Correct and incorrect password validation should be covered.
  Admin forms should not echo the raw bypass value.

### [Medium] Production Configuration Does Not Fail Closed on Required Secrets and Key Protection
- Confidence: High
- Area: infra
- Files:
  - `src/core/settings/components/production.py:15-29`
  - `src/.env.example:28-31`
  - `src/authn/models/security/rsa_keypair.py:37-46`
  - `src/authn/services/rsa_manager.py:103-109`
  - `.github/workflows/deploy-backend.yml:60-82`
- Problem:
  Production settings fall back to insecure default values for key security inputs, and RSA private-key encryption is documented as required in production but is not enforced or injected by the deployment path.
- Why it matters:
  A misconfigured production deployment can boot with a predictable `SECRET_KEY`, placeholder DB credentials, or unencrypted RSA private keys instead of failing fast.
- Evidence:
  `SECRET_KEY` defaults to `"change-me-in-production"`; database values default to generic placeholders; `RSA_KEY_PASSPHRASE` is optional in model/service code and is not validated in the backend deployment workflow.
- Recommendation:
  Raise `ImproperlyConfigured` when required production variables are missing and make `RSA_KEY_PASSPHRASE` mandatory in production if key material must be encrypted at rest.
- Suggested tests:
  Importing production settings without required env vars should fail.
  Production startup should fail when `RSA_KEY_PASSPHRASE` is missing.
  Key generation should assert encrypted private-key output when the passphrase is configured.

### [Medium] Mail Services Ignore the Configured Dev Email Backend and Fall Back to Real SMTP
- Confidence: High
- Area: backend
- Files:
  - `src/core/settings/dev.py:23-27`
  - `src/core/models/base/service_credentials.py:150-205`
  - `src/authn/services/email/send_email.py:80-142`
  - `src/event/services/ticket_mail.py:70-166`
- Problem:
  Development settings specify a console email backend, but the auth and ticket mail services explicitly create SMTP connections and fall back to default `smtp.gmail.com` settings when no `EmailServiceConfig` row exists.
- Why it matters:
  Fresh dev/test environments make unexpected outbound SMTP attempts, local email flows fail noisily instead of using a safe local backend, and tests can hide mail misconfiguration behind logged exceptions.
- Evidence:
  `EmailServiceConfig.load()` returns an unsaved default instance when the table is empty, with `smtp_host="smtp.gmail.com"`. Both mail services call `get_connection(backend="django.core.mail.backends.smtp.EmailBackend", ...)` directly. During this review, the backend test suite passed but emitted repeated `SMTPSenderRefused` traces from these code paths.
- Recommendation:
  In dev/test, honor Django's configured `EMAIL_BACKEND`, or make the fallback state explicitly unconfigured and refuse SMTP attempts unless a real active mail config exists.
- Suggested tests:
  With no `EmailServiceConfig`, dev/test email flows should use console or locmem backends.
  No external SMTP connection should be attempted in dev/test.
  Production should fail predictably when required mail config is absent.

### [Medium] Event Archive Pages Are Not Scoped to the Selected Event or Semester
- Confidence: High
- Area: frontend
- Files:
  - `pages/src/pages/EventArchivePage/EventArchivePage.tsx:13-14`
  - `pages/src/pages/EventArchivePage/EventArchivePage.tsx:52-71`
  - `pages/src/hooks/usePastProjectsData.ts:37-40`
  - `pages/src/features/projects/api.ts:102-105`
  - `pages/src/components/ScheduleGrid/ScheduleGrid.tsx:52-60`
  - `pages/src/components/ScheduleGrid/ScheduleGrid.tsx:125-129`
  - `src/projects/views/all_past_projects.py:10-34`
- Problem:
  Each event archive page fetches the flat `/projects/past-all/` dataset and renders it without filtering to the selected archive event or semester.
- Why it matters:
  The archive schedule can display the wrong team's row when two semesters share the same class/order/track coordinates, and the archive projects table shows unrelated historical projects.
- Evidence:
  `usePastProjectsData()` always returns all past projects. `ScheduleGrid` keys cells by class plus `order-track`, not by semester. `EventArchivePage` passes the full dataset directly to both the schedule and the table.
- Recommendation:
  Add a semester- or event-scoped backend endpoint, or filter the dataset client-side using an explicit semester/event key before rendering.
- Suggested tests:
  Each archive route should render only rows for its configured semester.
  Schedule cell collisions across semesters should be impossible.
  The projects table should exclude unrelated semesters.

### [Medium] CMS and News HTML Is Rendered Without a Central Sanitization Layer
- Confidence: Medium
- Area: cross-cutting
- Files:
  - `src/cms/services/news/scraper.py:31-35`
  - `src/cms/services/news/sync.py:115-117`
  - `pages/src/pages/NewsDetailPage/NewsDetailPage.tsx:80-84`
  - `pages/src/components/CMS/blocks/content/RichTextBlock.tsx:11-13`
  - `pages/src/components/Layout/Footer/Footer.tsx:75-77`
  - `pages/src/components/Layout/Footer/Footer.tsx:102-104`
- Problem:
  HTML from CMS block data and scraped news content is passed through to multiple `dangerouslySetInnerHTML` sinks, and no central sanitization layer was visible in the reviewed code.
- Why it matters:
  A compromised or malformed upstream content source, or an admin-entered unsafe payload, can become a stored XSS issue on public pages.
- Evidence:
  The scraper stores raw `decode_contents()` into `article.content`, sync persists it directly, and the frontend renders that HTML verbatim. Multiple CMS and footer blocks also render raw HTML fields directly.
- Recommendation:
  Sanitize HTML at ingest or serialization time, define an allowlist of tags and attributes, and centralize frontend rendering through a single safe HTML component.
- Suggested tests:
  Known XSS payloads should be stripped or escaped before persistence or rendering.
  Render tests should verify that unsafe attributes and scripts never reach the DOM.

### [Medium] Token Refresh Requests Are Not Deduplicated Across Concurrent 401s
- Confidence: High
- Area: frontend
- Files:
  - `pages/src/shared/auth/client.ts:25-55`
- Problem:
  If several authenticated requests fail with `401` at the same time, each one can trigger its own `/authn/refresh/` request.
- Why it matters:
  Parallel refresh races can overwrite token state, retry requests with stale credentials, and create hard-to-reproduce session bugs.
- Evidence:
  The interceptor checks only `originalRequest._retry`; there is no shared in-flight refresh promise. This contrasts with the layout-fetch path, which does implement in-flight deduplication.
- Recommendation:
  Introduce a shared refresh promise so only one refresh request is active at a time and all failed requests await the same result.
- Suggested tests:
  Multiple simultaneous `401` responses should cause exactly one refresh call.
  All queued requests should resume with the same new access token.
  Refresh failure should clear auth state exactly once.

### [Medium] CI/CD Gives Incomplete Production Validation
- Confidence: High
- Area: infra
- Files:
  - `.github/workflows/ci.yml:55-59`
  - `src/manage.py:10`
  - `src/core/settings/dev.py:52-56`
  - `.github/workflows/deploy-frontend.yml:50-80`
- Problem:
  The backend test suite runs under `core.settings.dev` on SQLite, and the frontend deployment workflow exits after starting an Amplify deployment instead of verifying the terminal result.
- Why it matters:
  A green pipeline does not fully validate production-faithful database behavior or prove that the frontend actually deployed successfully.
- Evidence:
  CI invokes `python manage.py test --settings=core.settings.dev`; `manage.py` defaults to `core.settings.dev`, which uses SQLite. Separately, the Amplify workflow starts the deployment and prints success without polling final job status.
- Recommendation:
  Run the Django test suite against PostgreSQL using `core.settings.ci` or equivalent production-like settings, and poll Amplify deployment status to a terminal success/failure state.
- Suggested tests:
  Add a PostgreSQL-backed test job that runs the full backend suite.
  Add workflow logic that fails when Amplify deployment reaches a failed terminal state.

### [Low] Raw Exception Text Is Returned to Clients on Some Public or Semi-Public Endpoints
- Confidence: High
- Area: backend
- Files:
  - `src/authn/views/verification/public_key.py:27-39`
  - `src/event/views/registration.py:199-205`
  - `src/event/views/registration.py:222-236`
- Problem:
  Several endpoints return `str(exc)` or formatted exception text directly to the client.
- Why it matters:
  Internal provider failures, configuration mistakes, or operational details can leak through the API surface.
- Evidence:
  `PublicKeyView` returns `Failed to retrieve public key: {e}`. The phone-code send/verify endpoints return `{"detail": str(exc)}` for generic failures.
- Recommendation:
  Log detailed exceptions server-side and return stable, generic client-facing error messages.
- Suggested tests:
  Mock internal failures and assert sanitized response bodies while preserving server-side logging.

### [Low] Desktop Main Menu Dropdowns Are Effectively Mouse-Hover Only
- Confidence: High
- Area: frontend
- Files:
  - `pages/src/components/Layout/MainMenu/MainMenu.tsx:29-31`
  - `pages/src/components/Layout/MainMenu/parts/MenuTree.tsx:35-58`
  - `pages/src/components/Layout/MainMenu/styles/desktop-dropdowns.css:89-90`
  - `pages/src/components/Layout/MainMenu/styles/desktop-dropdowns.css:154-155`
- Problem:
  Parent menu items expose `aria-expanded`, but opening behavior is driven by hover and a no-op toggle handler instead of keyboard-usable interaction.
- Why it matters:
  Keyboard users cannot reliably open or traverse the desktop dropdown hierarchy.
- Evidence:
  `handleDesktopToggle()` does nothing. `MenuTree` opens top-level items via `onMouseEnter`, and CSS reveals nested menus via `:hover` selectors.
- Recommendation:
  Implement button-like keyboard toggling for expandable menu items and ensure submenu visibility is driven by state rather than hover alone.
- Suggested tests:
  Keyboard interaction tests should verify that `Enter`, `Space`, and arrow-key flows can open and traverse menus.
  Accessibility smoke tests should confirm correct `aria-expanded` behavior.

## 4. Positive Observations

- Backend app boundaries are generally clear: `authn`, `cms`, `event`, `projects`, `mail`, and `core` each have recognizable responsibilities and mostly consistent `models` / `views` / `serializers` / `services` / `admin` / `tests` structure.
- The backend test footprint is strong. The local run completed successfully with `695` passing Django tests, covering CMS, auth, events, projects, core middleware, admin behavior, and settings behavior.
- The event registration model uses a database-level uniqueness constraint for one registration per member/event, which is the right place to enforce that invariant: `src/event/models/registration/registration.py:56-60`.
- Frontend layout loading is handled thoughtfully with session cache reuse and in-flight request deduplication: `pages/src/components/Layout/LayoutProvider/LayoutProvider.tsx:44-96` and `pages/src/features/layout/api.ts:125-138`.
- Health-check behavior and production cache fallback both have targeted tests, which is valuable operational coverage: `src/core/tests/middleware/test_health_middleware.py`, `src/core/tests/middleware/test_health_cors.py`, and `src/core/tests/settings/test_prod_cache.py`.
- `archive/` is clearly marked as historical material and separated from active runtime code, which reduces accidental coupling.

## 5. Testing Assessment

Existing coverage strengths:

- Backend coverage is broad and practical. The suite covers core request paths, admin flows, CMS behavior, event registration/tickets, auth flows, and several operational concerns.
- Frontend tests at least protect route registration and import-level regressions.
- Local execution was successful:
  - Backend: `695` passed, `1` skipped
  - Frontend: `55` passed

Missing coverage areas:

- No visible tests for `src/mail/views.py` / `/mail/magic-login/`, even though it is a public auth-adjacent endpoint.
- No tests for the `phone_verified` trust boundary in event registration.
- No tests asserting that anonymous live-preview requests cannot access draft CMS data.
- No replay/one-time-use tests for ticket-login and unsubscribe-login flows.
- Frontend tests are still heavily weighted toward smoke/import coverage; most stateful user flows are untested.
- No full PostgreSQL-backed backend test run is present in CI; PostgreSQL is only used for migration validation.

Highest-priority tests to add:

1. Anonymous vs staff/signed access tests for CMS live preview.
2. Event registration tests that require server-side proof for verified phones.
3. Replay, expiry, and revocation tests for ticket-login, unsubscribe-login, and ticket access tokens.
4. Authenticated subscribe-flow tests that preserve existing profile fields.
5. Semester-scoped archive page tests that assert the correct rows appear in schedule and table views.
6. Frontend auth-refresh concurrency tests that ensure only one refresh occurs under parallel `401` responses.
7. PostgreSQL-backed backend test execution in CI, not just migration checks.

## 6. Architecture and Maintainability Assessment

Structure and modularity:

- The overall repository split is sound: Django backend under `src/`, React frontend under `pages/`, active docs under `docs/`, deployment material under `.github/` and `aws/`, and explicitly non-runtime history under `archive/`.
- Backend modules are mostly cohesive, and the service layer is used often enough to keep views from becoming monoliths.

Separation of concerns:

- The strongest separation appears in CMS/layout and event domains, where data access and serialization are fairly deliberate.
- The weakest separation is around trust-sensitive cross-cutting behavior:
  - token issuance logic is spread across `event`, `authn`, and `mail` with inconsistent one-time/expiry semantics
  - HTML trust decisions are spread across backend ingestion and multiple frontend renderers
  - email behavior bypasses the Django environment abstraction and reaches directly for SMTP

Coupling and cohesion concerns:

- The event archive page currently depends on a generic flat historical dataset and reconstructs event-specific views client-side. That is a brittle frontend/backend contract and should become an explicit API contract.
- Some frontend pages implement their own fetch lifecycle patterns while others use safer cancellation or dedupe patterns. The codebase would benefit from a more uniform async data-loading approach.

Refactoring priorities:

1. Unify token lifecycle handling for all email-based login/access flows.
2. Centralize HTML sanitization and rendering boundaries.
3. Introduce a single shared pattern for frontend async requests with cancellation, dedupe, and error handling.
4. Make environment-sensitive services respect settings instead of bypassing framework abstractions.

## 7. Security and Operations Assessment

Auth and permissions:

- The codebase generally uses DRF permission classes correctly, but the confirmed exceptions are significant: anonymous CMS live-preview access and client-trusted phone verification.
- Auth token behavior is inconsistent across related flows; `MagicLoginToken` is one-time-use, but ticket and unsubscribe flows are not.

Secrets and deployment:

- GitHub Actions is used to source deployment secrets, but the current ECS rendering step still materializes them into plain task-definition environment variables.
- Production settings do not fail fast when required secret inputs are missing.

Validation and admin safety:

- The maintenance bypass secret is not handled with normal password hygiene.
- Public error handling still leaks raw exception text in some places.

Operational reliability:

- The backend test suite is healthy, but CI still gives incomplete production confidence because it does not run the application tests on PostgreSQL.
- The frontend deploy workflow can report success before Amplify has actually completed deployment.
- Mail behavior in dev/test is not isolated cleanly from real SMTP fallback behavior.

## 8. Prioritized Action Plan

1. Immediate fixes

- Lock down `CMSLivePreviewView` so anonymous requests cannot fall back to draft page data.
- Remove client control over `phone_verified` and require server-validated proof.
- Move ECS secrets from plain `environment` entries to AWS-managed secret references.
- Fix the authenticated subscribe flow so existing profile fields are loaded or preserved.

2. Short-term improvements

- Add one-time-use or revocation controls to ticket and unsubscribe login flows, and add expiry to ticket access tokens.
- Hash the maintenance bypass password and stop exposing it as plaintext in admin.
- Make production settings fail fast when required secrets or key-protection inputs are missing.
- Stop mail services from bypassing the configured dev/test email backend.

3. Medium-term refactors

- Replace the event archive's generic flat-data dependency with an event- or semester-scoped API contract.
- Introduce a central safe-HTML pipeline for CMS/news content.
- Add shared frontend request primitives for cancellation, dedupe, and consistent error states.

4. Testing improvements

- Add backend tests for live-preview authorization, phone-verification proof handling, token replay prevention, and `/mail/magic-login/`.
- Expand frontend tests beyond smoke coverage to include subscribe, archive, auth-refresh, and menu interaction behavior.
- Run the full backend suite against PostgreSQL in CI.
- Make the frontend deployment workflow wait for and assert the final Amplify deployment result.

## 9. Appendix: Files or Areas Reviewed

Major directories and components reviewed:

- `README.md`, `pyproject.toml`, `CONTRIBUTING.md`
- `src/core/`:
  - settings entrypoints and components
  - middleware, top-level URLs, views, admin, models, tests
- `src/authn/`:
  - URLs, public key and auth flows, profile/contact APIs, token/login utilities, RSA handling, tests
- `src/cms/`:
  - CMS page/live-preview/news/layout APIs, models, services, admin, tests
- `src/event/`:
  - event registration, tickets, ticket login, schedule/current-project views, serializers, services, tests
- `src/projects/`:
  - current/past project APIs, share flows, tests
- `src/mail/`:
  - magic login view/model, admin/import services, tests
- `pages/src/`:
  - router, page components, shared auth/api clients, layout provider, CMS rendering, maintenance mode, tests
- `.github/workflows/`:
  - CI, lint, backend deploy, frontend deploy
- `aws/task-definition.json`
- `docs/architecture/` and related active documentation areas
- `archive/README.md` and top-level archive structure
