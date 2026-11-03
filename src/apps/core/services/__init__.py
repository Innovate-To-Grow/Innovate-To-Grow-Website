"""
Map of the service subsystems that live under ``apps.core``.

``core`` is the framework app. Its ``services/`` tree holds infrastructure that
several apps share and that names no business app: domain behaviour belongs in
the owning app (e.g. the Bedrock client and the assistant's query tools now live
in ``system_intelligence``, the sitemap in ``cms``). Read this before adding a
module: put it in the owning app unless it is genuinely shared. ``core`` must not
import business apps at module level (``scripts/ci/check_python_dependencies.py``);
apps plug into shared machinery through registration hooks instead.
Consumers below are the apps that import each path today (verified, excluding
``core``'s own modules).

======================  ====================================================  ==================================================
Subsystem               What it is                                            Importing apps
======================  ====================================================  ==================================================
``aws/``                Shared AWS credential resolution, the one SMS send     ``authn``, ``event``, ``mail``
                        (``sms_send``, paced by ``delivery_rates``) and the
                        SES / SMS limit reads (``quotas``)
``background_jobs/``    Durable outbox: queue, worker (claims by priority,     ``authn``, ``cms``, ``event``, ``mail``
                        skipping gated delivery lanes), retry.
                        Apps register job kinds from ``AppConfig.ready()``
                        with ``register_job_kind`` (dotted handler paths;
                        delivery kinds also name their family and lane).
``credential_store/``   Versioned private-key store, read by pinned version:   ``core`` only (system check, Graph and Gmail keys)
                        Secrets Manager (prod), 0600 files (dev), memory
                        (tests). The database keeps only ARN + version id.
``delivery_rates/``     Delivery-rate control for every channel (Graph, SES,   ``authn``, ``event``, ``mail`` (job-kind
                        SMTP, Gmail IMAP and API, SMS): Smart and manual      and campaign lanes); in ``core``, ``email/``
                        rate, pacing, budgets, breakers, AWS limit reads.     and ``aws/sms_send`` admit every message;
                                                                              ``mail`` admits each Gmail IMAP session
                        ``rules/`` is pure; ``runtime/`` uses the state rows;
                        ``families`` gates the worker's claims; ``adapters/``
                        turn provider answers into rate signals.
``db_tools/``           ``safe_orm``: the read-only ORM sandbox (field /       ``cli_admin``, ``system_intelligence``
                        filter allowlists, ``MAX_ROWS``)
``email/``              Provider-neutral MIME + SES/SMTP/Graph/Gmail API       ``authn``, ``event``, ``mail``
                        delivery over one bounded HTTPS ``transport``;
                        ``graph/credential/`` installs the Graph certificate
                        and ``gmail/key/`` the Gmail service-account key
                        (both in ``credential_store``); ``graph/`` and
                        ``gmail/access_check/`` record the go-live evidence
``helpers/``            In-process task runner + sheet formula safety         ``authn``, ``event``, ``mail``, ``system_intelligence``
``legacy_access/``      Signed access to the read-only legacy site viewer      ``core`` only (legacy_view, admin, views)
``request_limits/``     Inbound request limits for every route (one           ``core`` (its middleware); apps plug in from
                        middleware): scopes, priority tiers, Smart limiting    ``ready()`` with ``register_scope`` /
                        (shed P3 → P2 → P1, never P0), tier slots, abuse      ``register_exemption`` /
                        escalation; ``rules/`` is pure, ``runtime/`` holds     ``register_identity_resolver`` /
                        counters, heartbeats and the Smart state;             ``register_priority_check`` or a view's
                        ``view_limits`` gives per-view throttles their live    ``rate_limit_scope``; ``authn``, ``cms``,
                        policy rate, ``priority`` gates P0 promotion.         ``event``, ``mail``, ``projects``,
                                                                              ``cli_admin``, ``system_intelligence``
                                                                              (``view_limits`` throttle bases)
``status/``             Infrastructure status dashboard client                 ``core`` only (admin infrastructure status)
======================  ====================================================  ==================================================

Extracting ``background_jobs`` or ``db_tools`` into their own apps would need new
Django app labels — and app labels are stored **in the database**
(``Member.admin_apps``, read by ``apps.core.utils.access``), so it requires a data
migration. See ``docs/architecture/repository-structure.md``.

Structure limits are enforced by
``apps/core/tests/services/test_core_services_structure.py``: at most 200
*physical* lines per file and 10 ``.py`` files (``__init__.py`` included) per
directory in this tree. These are stricter than, and counted differently from,
the repository-wide limits in ``docs/architecture/code-quality.md``.
"""
