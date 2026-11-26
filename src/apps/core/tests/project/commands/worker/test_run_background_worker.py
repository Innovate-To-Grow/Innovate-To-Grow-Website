from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from apps.core.management.commands import run_background_worker
from apps.core.management.operations import email_maintenance, worker_maintenance
from apps.core.services.delivery_rates.lifecycle.maintenance import MaintenanceResult

NOTHING_CLEANED = {"expired_challenges": 0, "deleted_challenges": 0, "deleted_requests": 0}
NOTHING_MAINTAINED = MaintenanceResult(limits_read=0, buckets_purged=0, states_purged=0)
NO_IMPORTS_PURGED = {"expired": 0, "blanked": 0, "deleted": 0}
NOTHING_COUNTED = {"graph": 0, "ses": 0, "inbound": 0, "busy": False}


HELPDESK_NOTHING_PURGED = {
    "automated_bodies": 0,
    "spam_bodies": 0,
    "closed_bodies": 0,
    "attachments": 0,
    "tickets": 0,
}
HELPDESK_NOTHING_AUTOMATED = {"auto_closed": 0, "sla_breaches": 0}


LOGGER_NAME = "apps.core.management.commands.run_background_worker"


# The maintenance services, in task order, with what each returns when there is nothing to do.
MAINTENANCE_SERVICES = {
    "purge_retired_auth_keypairs": 0,
    "purge_expired_public_assistant_budgets": 0,
    "cleanup_expired_records": NOTHING_CLEANED,
    "clear_expired_sessions": 0,
    "purge_expired_failure_windows": 0,
    "purge_member_imports": NO_IMPORTS_PURGED,
    "run_delivery_rate_maintenance": NOTHING_MAINTAINED,
    "active_certificate_expiry": None,
    "ensure_bounce_scan_scheduled": False,
    "ensure_delivery_trace_scheduled": False,
    "count_bounced_addresses": NOTHING_COUNTED,
    "refresh_bounced_address_links": 0,
    "sync_sms_opt_outs": None,
    "purge_expired_email_telemetry": {"emails": 0, "bounces": 0},
    "purge_expired_inbound_queue": 0,
    "purge_finished_bounce_scans": 0,
    "purge_finished_delivery_traces": 0,
    "ensure_helpdesk_intake_scheduled": False,
    "ensure_helpdesk_ingest_scheduled": False,
    "run_helpdesk_automation": HELPDESK_NOTHING_AUTOMATED,
    "purge_expired_helpdesk": HELPDESK_NOTHING_PURGED,
    "purge_finished_helpdesk_ingests": 0,
    "purge_finished_helpdesk_intake_scans": 0,
    "ensure_inbox_poll_scheduled": False,
    "purge_finished_inbox_polls": 0,
}


def service_module(name):
    """Where the maintenance tasks look a service up: ``email_maintenance`` for the email tasks, else
    ``worker_maintenance``."""
    return email_maintenance if hasattr(email_maintenance, name) else worker_maintenance


def patch_maintenance(**side_effects):
    """Patch the maintenance services; ``side_effects`` maps a service name to a side effect."""
    patchers = []
    for name, return_value in MAINTENANCE_SERVICES.items():
        if name in side_effects:
            patchers.append(patch.object(service_module(name), name, side_effect=side_effects[name]))
        else:
            patchers.append(patch.object(service_module(name), name, return_value=return_value))
    return patchers


@contextmanager
def patch_worker(returns):
    """Patch each name in ``returns`` to return its value (a maintenance service where the tasks look it up, in
    ``worker_maintenance`` or ``email_maintenance``; anything else in ``run_background_worker``); yield the mocks by
    name.

    One ExitStack holds every patch, so the worker can gain any number of services: a single ``with`` statement of
    more than 20 context managers does not compile on Python 3.11 ("too many statically nested blocks")."""
    with ExitStack() as stack:
        yield {
            name: stack.enter_context(
                patch.object(
                    service_module(name) if name in MAINTENANCE_SERVICES else run_background_worker,
                    name,
                    return_value=value,
                )
            )
            for name, value in returns.items()
        }


# The batched services are called with the stop check; the others take no argument.
BATCHED_SERVICES = (
    "cleanup_expired_records",
    "clear_expired_sessions",
    "purge_expired_failure_windows",
    "purge_member_imports",
    "count_bounced_addresses",
    "refresh_bounced_address_links",
    "sync_sms_opt_outs",
    "purge_expired_email_telemetry",
    "purge_expired_inbound_queue",
    "run_helpdesk_automation",
    "purge_expired_helpdesk",
)


def assert_each_service_ran_once(test_case, mocks, should_stop=None):
    for name, mock in mocks.items():
        if name in BATCHED_SERVICES:
            mock.assert_called_once_with(should_stop=should_stop)
        else:
            mock.assert_called_once_with()
