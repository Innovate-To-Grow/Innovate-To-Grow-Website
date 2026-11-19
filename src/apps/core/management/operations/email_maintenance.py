"""The background worker's email maintenance tasks: the Graph certificate expiry check, the bounce scan and Message
Trace scheduling, the bounced-address counting and the email telemetry retention. ``worker_maintenance`` lists them
in ``MAINTENANCE_TASKS``, in their order among the other tasks."""

import logging

from apps.core.services.email.bounces import ensure_scheduled as ensure_bounce_scan_scheduled
from apps.core.services.email.bounces import purge_finished_jobs as purge_finished_bounce_scans
from apps.core.services.email.graph.credential import expiry
from apps.core.services.email.graph.credential.expiry import active_certificate_expiry
from apps.core.services.email.graph.tracing import ensure_scheduled as ensure_delivery_trace_scheduled
from apps.core.services.email.graph.tracing import purge_finished_jobs as purge_finished_delivery_traces
from apps.core.services.email.inbound import purge_expired as purge_expired_inbound_queue
from apps.core.services.email.telemetry.retention import purge_expired as purge_expired_email_telemetry
from apps.mail.services.email_monitoring.addresses.aggregate import refresh_all as refresh_bounced_address_links
from apps.mail.services.email_monitoring.addresses.aggregate import run as count_bounced_addresses

# The worker command's logger: maintenance logs under the same name as the rest of the worker.
logger = logging.getLogger("apps.core.management.commands.run_background_worker")

# One fixed line (a log metric filter can match its prefix); only the day count varies.
GRAPH_EXPIRY_WARNING = "Microsoft Graph certificate expiry warning: %d days left; install the renewed certificate"
GRAPH_EXPIRED_WARNING = "Microsoft Graph certificate expiry warning: expired; install the renewed certificate"


def check_graph_certificate_expiry(should_stop=None) -> None:
    # The active Graph config's current certificate, from GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS before expiry on.
    status = active_certificate_expiry()
    if status is None or status.level in (expiry.OK, expiry.NOT_YET_VALID):
        return
    if status.level == expiry.EXPIRED:
        logger.warning(GRAPH_EXPIRED_WARNING)
    else:
        logger.warning(GRAPH_EXPIRY_WARNING, status.days_left)


def schedule_bounce_scans(should_stop=None) -> None:
    # The bounce scans chain themselves (each queues the next); this restarts the chain at start-up or if it broke.
    if ensure_bounce_scan_scheduled():
        logger.debug("Queued an email bounce scan")


def schedule_delivery_traces(should_stop=None) -> None:
    # The Message Trace syncs chain themselves while the Graph config's Message Trace toggle is on (off by default);
    # this starts the chain once it is switched on and restarts it if it broke.
    if ensure_delivery_trace_scheduled():
        logger.debug("Queued an email delivery trace sync")


def count_bounced(should_stop=None) -> None:
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


def purge_email_telemetry(should_stop=None) -> None:
    # Outgoing-email telemetry, bounce records and inbound queue rows past EMAIL_MONITORING's retention, and finished
    # bounce scan and delivery trace jobs.
    result = {
        **purge_expired_email_telemetry(should_stop=should_stop),
        "inbound": purge_expired_inbound_queue(should_stop=should_stop),
        "scan_jobs": purge_finished_bounce_scans(),
        "trace_jobs": purge_finished_delivery_traces(),
    }
    if any(result.values()):
        logger.info(
            "Email telemetry retention: deleted %(emails)d emails, %(bounces)d bounce records, %(inbound)d inbound "
            "queue rows, %(scan_jobs)d finished bounce scan jobs and %(trace_jobs)d finished delivery trace jobs",
            result,
        )
