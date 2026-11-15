"""The background worker's periodic maintenance tasks, in their order (``MAINTENANCE_TASKS``).
``commands/run_background_worker.py`` runs them with ``run_maintenance`` every ``--maintenance-seconds``."""

import logging

from apps.authn.services.login_guard import purge_expired_failure_windows
from apps.authn.services.members.import_.review.staging.purge import purge_member_imports
from apps.authn.services.security.rsa_manager import purge_retired_auth_keypairs
from apps.authn.services.send_verification import cleanup_expired_records, clear_expired_sessions
from apps.core.services.delivery_rates import run_maintenance as run_delivery_rate_maintenance
from apps.core.services.email.bounces import ensure_scheduled as ensure_bounce_scan_scheduled
from apps.core.services.email.bounces import purge_finished_jobs as purge_finished_bounce_scans
from apps.core.services.email.graph.credential import expiry
from apps.core.services.email.graph.credential.expiry import active_certificate_expiry
from apps.core.services.email.inbound import purge_expired as purge_expired_inbound_queue
from apps.core.services.email.telemetry.retention import purge_expired as purge_expired_email_telemetry
from apps.helpdesk.services.ingest.pipeline.jobs import ensure_scheduled as ensure_helpdesk_ingest_scheduled
from apps.helpdesk.services.ingest.pipeline.jobs import purge_finished_jobs as purge_finished_helpdesk_ingests
from apps.helpdesk.services.intake.jobs import ensure_scheduled as ensure_helpdesk_intake_scheduled
from apps.helpdesk.services.intake.jobs import purge_finished_jobs as purge_finished_helpdesk_intake_scans
from apps.helpdesk.services.tickets.retention import purge_expired as purge_expired_helpdesk
from apps.mail.services.email_monitoring.addresses.aggregate import refresh_all as refresh_bounced_address_links
from apps.mail.services.email_monitoring.addresses.aggregate import run as count_bounced_addresses
from apps.mail.services.sms.policy.opt_out_sync import run_scheduled as sync_sms_opt_outs
from apps.system_intelligence.services.public_assistant import purge_expired_public_assistant_budgets

# The worker command's logger: maintenance logs under the same name as the rest of the worker.
logger = logging.getLogger("apps.core.management.commands.run_background_worker")

# One fixed line (a log metric filter can match its prefix); only the day count varies.
GRAPH_EXPIRY_WARNING = "Microsoft Graph certificate expiry warning: %d days left; install the renewed certificate"
GRAPH_EXPIRED_WARNING = "Microsoft Graph certificate expiry warning: expired; install the renewed certificate"


def _purge_retired_keys(should_stop=None) -> None:
    if purge_retired_auth_keypairs():
        # Keep key material and values derived from the key store out of logs. The static event is enough for
        # operators; detailed counts belong in controlled metrics.
        logger.info("Purged retired RSA keypair rows")


def _purge_public_assistant_budgets(should_stop=None) -> None:
    if purge_expired_public_assistant_budgets():
        # Do not log counts or IP-derived identifiers. Operators only need confirmation that maintenance is active.
        logger.info("Purged expired public assistant budget rows")


def _cleanup_send_verification(should_stop=None) -> None:
    result = cleanup_expired_records(should_stop=should_stop)
    if any(result.values()):
        logger.info(
            "Send verification cleanup: expired %(expired_challenges)d challenges; deleted %(deleted_challenges)d "
            "challenges and %(deleted_requests)d send requests",
            result,
        )


def _clear_expired_sessions(should_stop=None) -> None:
    cleared = clear_expired_sessions(should_stop=should_stop)
    if cleared:
        logger.info("Cleared %d expired sessions", cleared)


def _purge_login_failure_windows(should_stop=None) -> None:
    # Only windows that have already ended are deleted, so this never lifts a password-login lockout early.
    if purged := purge_expired_failure_windows(should_stop=should_stop):
        logger.info("Purged %d expired login failure windows", purged)


def _purge_member_imports(should_stop=None) -> None:
    # Unapplied member imports past their lifetime, and the sheet values / rows of old applied ones (MEMBER_IMPORT).
    result = purge_member_imports(should_stop=should_stop)
    if any(result.values()):
        logger.info(
            "Member import retention: deleted %(expired)d expired and %(deleted)d old imports; blanked %(blanked)d",
            result,
        )


def _delivery_rate_maintenance(should_stop=None) -> None:
    # Re-read the provider limits that are due (SES, AWS SMS) and purge old usage buckets and idle state rows.
    result = run_delivery_rate_maintenance()
    if result.buckets_purged or result.states_purged:
        logger.info(
            "Delivery-rate maintenance: purged %d usage buckets and %d idle states",
            result.buckets_purged,
            result.states_purged,
        )


def _check_graph_certificate_expiry(should_stop=None) -> None:
    # The active Graph config's current certificate, from GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS before expiry on.
    status = active_certificate_expiry()
    if status is None or status.level in (expiry.OK, expiry.NOT_YET_VALID):
        return
    if status.level == expiry.EXPIRED:
        logger.warning(GRAPH_EXPIRED_WARNING)
    else:
        logger.warning(GRAPH_EXPIRY_WARNING, status.days_left)


def _schedule_bounce_scans(should_stop=None) -> None:
    # The bounce scans chain themselves (each queues the next); this restarts the chain at start-up or if it broke.
    if ensure_bounce_scan_scheduled():
        logger.debug("Queued an email bounce scan")


def _count_bounced_addresses(should_stop=None) -> None:
    # Count new bounce reports, SES events and left-the-organisation notices per address (Email Monitoring → Bounced
    # addresses) before the retention purges delete old records, then re-check every address's member links. Never
    # changes a member or a contact.
    result = count_bounced_addresses(should_stop=should_stop)
    refreshed = refresh_bounced_address_links(should_stop=should_stop)
    notices = result.get("inbound", 0)
    if result["graph"] or result["ses"] or notices or refreshed:
        logger.info(
            "Bounced addresses: counted %d bounce reports, %d SES events and %d left-the-organisation notices; "
            "refreshed %d addresses",
            result["graph"],
            result["ses"],
            notices,
            refreshed,
        )


def _sync_sms_opt_outs(should_stop=None) -> None:
    # Read the sending number's opted-out list from AWS (read only) into Mail → SMS Opt-outs, when it is on in SMS
    # Settings; the sync records its own outcome and log line.
    sync_sms_opt_outs(should_stop=should_stop)


def _purge_email_telemetry(should_stop=None) -> None:
    # Outgoing-email telemetry, bounce records and inbound queue rows past EMAIL_MONITORING's retention, and finished
    # scan jobs.
    result = {
        **purge_expired_email_telemetry(should_stop=should_stop),
        "inbound": purge_expired_inbound_queue(should_stop=should_stop),
        "scan_jobs": purge_finished_bounce_scans(),
    }
    if any(result.values()):
        logger.info(
            "Email telemetry retention: deleted %(emails)d emails, %(bounces)d bounce records, %(inbound)d inbound "
            "queue rows and %(scan_jobs)d finished bounce scan jobs",
            result,
        )


def _schedule_helpdesk_intake(should_stop=None) -> None:
    # The helpdesk's own Inbox scan chains itself; this starts it at start-up and restarts it if the chain broke.
    if ensure_helpdesk_intake_scheduled():
        logger.debug("Queued a helpdesk intake scan")


def _schedule_helpdesk_ingest(should_stop=None) -> None:
    # The ingest is queued by each intake scan that records new mail and chains itself; this restarts it if mail waits.
    if ensure_helpdesk_ingest_scheduled():
        logger.debug("Queued a helpdesk ingest run")


def _purge_helpdesk(should_stop=None) -> None:
    # Ticket bodies, attachments and tickets past the retention periods set in Helpdesk → Settings.
    result = {
        **purge_expired_helpdesk(should_stop=should_stop),
        "ingest_jobs": purge_finished_helpdesk_ingests(),
        "intake_scans": purge_finished_helpdesk_intake_scans(),
    }
    if any(result.values()):
        logger.info(
            "Helpdesk retention: purged %(automated_bodies)d automated, %(spam_bodies)d spam and %(closed_bodies)d "
            "closed-ticket bodies and %(attachments)d attachments; deleted %(tickets)d tickets, %(ingest_jobs)d "
            "finished ingest jobs and %(intake_scans)d finished intake scans",
            result,
        )


# Periodic maintenance, run in this order every ``--maintenance-seconds`` (hourly by default). Each entry is
# ``(name, callable)``; ``run_maintenance`` isolates every call, so one failure never stops the worker or the rest.
# Every callable takes the stop check: the batched tasks (the three cleanups, the member import purge, the
# bounced-address counting, the email telemetry retention and the helpdesk retention) hand it to their batch loops, so
# a stop request ends them after the batch in flight; the two single-statement purges, the delivery-rate upkeep, the
# certificate expiry check, the scan and ingest scheduling and the SMS opt-out sync ignore it.
MAINTENANCE_TASKS = (
    ("Retired RSA key purge", _purge_retired_keys),
    ("Public assistant budget purge", _purge_public_assistant_budgets),
    ("Send verification cleanup", _cleanup_send_verification),
    ("Expired session cleanup", _clear_expired_sessions),
    ("Login failure window purge", _purge_login_failure_windows),
    ("Member import purge", _purge_member_imports),
    ("Delivery-rate maintenance", _delivery_rate_maintenance),
    ("Microsoft Graph certificate expiry check", _check_graph_certificate_expiry),
    ("Email bounce scan scheduling", _schedule_bounce_scans),
    ("Bounced address counting", _count_bounced_addresses),
    ("SMS opt-out sync", _sync_sms_opt_outs),
    ("Email telemetry retention", _purge_email_telemetry),
    ("Helpdesk intake scheduling", _schedule_helpdesk_intake),
    ("Helpdesk ingest scheduling", _schedule_helpdesk_ingest),
    ("Helpdesk retention", _purge_helpdesk),
)
