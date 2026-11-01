"""Record an access-check run as evidence: one ``MicrosoftGraphAccessCheck`` row, a log line and admin history.

Nothing recorded holds a token, a response body or message content: the probe results are fixed notes, statuses,
allow-listed error codes and Microsoft request ids.
"""

import logging

from django.contrib.admin.models import CHANGE, LogEntry

from apps.core.models import MicrosoftGraphAccessCheck
from apps.core.models.base.service_credentials.microsoft_graph import normalize_mailbox

from .report import AccessCheckReport
from .runner import run_access_check

logger = logging.getLogger(__name__)


def run_and_record(config, *, deny_mailbox: str, source: str, run_by=None, send: bool = True):
    """Run the check and store it; returns ``(report, MicrosoftGraphAccessCheck)``."""
    report = run_access_check(config, deny_mailbox=normalize_mailbox(deny_mailbox), send=send)
    return report, record(report, config, source=source, run_by=run_by)


def record(report: AccessCheckReport, config, *, source: str, run_by=None) -> MicrosoftGraphAccessCheck:
    check = MicrosoftGraphAccessCheck.objects.create(
        config=config,
        certificate_id=report.certificate_id,
        certificate_sha1=report.certificate_sha1,
        tenant_id=report.tenant_id,
        client_id=report.client_id,
        deny_mailbox=report.deny_mailbox,
        source=source,
        run_by=run_by if getattr(run_by, "pk", None) else None,
        results=[result.as_dict() for result in report.results],
        granted_roles=None if report.granted_roles is None else list(report.granted_roles),
        approved_roles=list(report.approved_roles),
        mailbox_restriction_passed=report.restriction_holds,
        roles_within_approval=report.roles_within_approval,
        complete=report.complete,
        permission_exception_reference=report.exception_reference,
        verdict=report.verdict,
    )
    logger.info(
        "graph_access_check verdict=%s restriction=%s complete=%s roles_within=%s sha1=%s config=%s source=%s",
        check.verdict,
        check.mailbox_restriction_passed,
        check.complete,
        check.roles_within_approval,
        check.certificate_sha1,
        config.pk,
        source,
    )
    if check.run_by_id:
        message = f"Ran the Microsoft Graph access check against {check.deny_mailbox}: {check.get_verdict_display()}."
        LogEntry.objects.log_actions(
            user_id=check.run_by_id, queryset=[config], action_flag=CHANGE, change_message=message, single_object=True
        )
    return check
