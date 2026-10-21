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
``aws/``                Shared AWS credential resolution + SNS SMS send        ``authn``, ``event``, ``mail``
``background_jobs/``    Durable outbox: queue, worker, retry, rate limit.      ``authn``, ``cms``, ``event``, ``mail``
                        Apps register job kinds from ``AppConfig.ready()``
                        with ``register_job_kind`` (dotted handler paths).
``db_tools/``           ``safe_orm``: the read-only ORM sandbox (field /       ``cli_admin``, ``system_intelligence``
                        filter allowlists, ``MAX_ROWS``)
``email/``              Provider-neutral MIME + SES/SMTP email delivery        ``authn``, ``event``, ``mail``
``helpers/``            In-process task runner + sheet formula safety         ``authn``, ``event``, ``mail``, ``system_intelligence``
``legacy_access/``      Signed access to the read-only legacy site viewer      ``core`` only (legacy_view, admin, views)
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
