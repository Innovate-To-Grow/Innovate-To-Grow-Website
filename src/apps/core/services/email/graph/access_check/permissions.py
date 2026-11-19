"""The Graph permission check: which application roles the current certificate's token carries, and what they allow.

Read-only and light: one fresh token, its ``roles`` claim read without trusting it (``roles.token_roles``), a
capability table (``GRAPH_FEATURE_PERMISSIONS``) and, when the Message Trace role is in the token or Message Trace is
switched on, one live trace request (``$top=1``, the last hour, the From address as sender). It sends no mail, needs
no deny mailbox and never writes a ``MicrosoftGraphAccessCheck``, so it can neither give nor withdraw go-live
evidence. Each run is stored as a ``MicrosoftGraphPermissionCheck`` (the latest 20 per config are kept).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.models import EmailServiceConfig, MicrosoftGraphPermissionCheck
from apps.core.models.base.service_credentials.microsoft_graph import MESSAGE_TRACE_ROLE

from ...sending.exceptions import EmailDeliveryError
from ...telemetry import text
from ..identity import auth
from ..identity.access import SEND, credential_for
from ..tracing import state as trace_state
from ..tracing.reader import GraphTraceBusy, GraphTraceError, GraphTraceNotPermitted, GraphTraceReader
from . import roles

logger = logging.getLogger(__name__)
Trace = MicrosoftGraphPermissionCheck.TraceResult
# (feature, the roles of which any one is enough), in the order the card lists them.
GRAPH_FEATURE_PERMISSIONS = (
    ("Send mail", ("Mail.Send",)),
    ("Bounce scan, admin inbox and helpdesk reading", ("Mail.Read", "Mail.ReadWrite")),
    ("Message Trace delivery status", (MESSAGE_TRACE_ROLE,)),
)
TRACE_APP_ID = "8bd644d1-64a1-4d4b-ae52-2e0cbf64e373"
CAVEAT = (
    "Exchange RBAC for Applications and Application Access Policy mailbox scoping never appear in the token, so this "
    "check cannot show which mailboxes the app may use: only the full access check proves the mailbox restriction."
)
RECORD_REFERENCE_FIRST = "Record the InfoSec exception reference before the next full access check."
TRACE_NOTES = {
    Trace.NOT_GRANTED: f"The token does not carry {MESSAGE_TRACE_ROLE} and Message Trace is off, so it was not probed.",
    Trace.NO_SERVICE_PRINCIPAL: (
        f"Microsoft answered 401: the service principal for the Message Trace app ({TRACE_APP_ID}) is missing or "
        "still provisioning (that can take hours)."
    ),
    Trace.NOT_CONSENTED: f"Microsoft answered 403: {MESSAGE_TRACE_ROLE} is not granted with admin consent.",
    Trace.THROTTLED: "Microsoft throttled the request; try again later.",
    Trace.NOT_CHECKED: "No token was issued, so nothing was probed.",
}
NO_SENDER = "The mailbox scope does not let the From address send, so Message Trace was not probed."
PROBE_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class Capability:
    feature: str
    permissions: tuple[str, ...]
    granted: bool | None  # None when the token's roles could not be read


@dataclass(frozen=True)
class PermissionReport:
    certificate_sha1: str
    token_ok: bool
    token_error: str
    granted_roles: tuple[str, ...] | None
    approved_roles: tuple[str, ...]
    exception_reference: str
    trace_result: str
    trace_note: str
    checked_at: datetime

    @property
    def extra_roles(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.granted_roles or ()) - set(self.approved_roles)))

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities(self.granted_roles)

    @property
    def warning(self) -> str:
        """What to do about roles beyond the approval: "" when there are none or a reference is recorded."""
        return RECORD_REFERENCE_FIRST if self.extra_roles and not self.exception_reference else ""

    def summary(self) -> str:
        if not self.token_ok:
            return f"No token was issued: {self.token_error}"
        if self.granted_roles is None:
            granted = "the token's roles could not be read"
        else:
            granted = f"granted {', '.join(self.granted_roles) or 'no application roles'}"
        extra = f"; beyond the approval: {', '.join(self.extra_roles)}" if self.extra_roles else ""
        return f"Permission check: {granted}{extra}. Message Trace: {Trace(self.trace_result).label.lower()}."


def capabilities(granted) -> tuple[Capability, ...]:
    """The capability table for the roles *granted* (None: unreadable, so every row is unknown)."""
    held = None if granted is None else set(granted)
    return tuple(
        Capability(feature, needs, None if held is None else bool(held & set(needs)))
        for feature, needs in GRAPH_FEATURE_PERMISSIONS
    )


@sensitive_variables()
def check_permissions(config) -> PermissionReport:
    """Request a fresh token with *config*'s current certificate and report what its roles allow."""
    certificate = config.current_certificate
    facts = {
        "certificate_sha1": certificate.sha1_thumbprint if certificate is not None else "",
        "approved_roles": roles.approved_roles(),
        "exception_reference": config.permission_exception_reference,
    }
    timeout = settings.GRAPH_ACCESS_CHECK_TIMEOUT_SECONDS
    try:
        credential = credential_for(config)
        # A cached token could predate a change OIT made: its roles must show the grant as it is now.
        auth.forget_access_token(credential)
        token = auth.get_access_token(credential, timeout=timeout)
    except EmailDeliveryError as exc:
        error = text.scrub(str(exc))
        return _report(facts, False, error, None, Trace.NOT_CHECKED, TRACE_NOTES[Trace.NOT_CHECKED])
    granted = roles.token_roles(token)
    if MESSAGE_TRACE_ROLE in (granted or ()) or config.message_trace_enabled:
        result, note = probe_trace(config, timeout=timeout)
    else:
        result, note = Trace.NOT_GRANTED, TRACE_NOTES[Trace.NOT_GRANTED]
    return _report(facts, True, "", granted, result, note)


def _report(facts, token_ok, token_error, granted, result, note) -> PermissionReport:
    return PermissionReport(
        token_ok=token_ok,
        token_error=token_error,
        granted_roles=granted,
        trace_result=result,
        trace_note=note,
        checked_at=timezone.now(),
        **facts,
    )


def probe_trace(config, *, timeout: float) -> tuple[str, str]:
    """One Message Trace request for the From address (``$top=1``, the last hour): ``(TraceResult, note)``."""
    sender = text.address(EmailServiceConfig.load().from_email)
    if not sender or not config.allows(sender, SEND):
        return Trace.ERROR, NO_SENDER
    now = timezone.now()
    try:
        GraphTraceReader(config, sender, timeout=timeout).page(now - PROBE_WINDOW, now, top=1)
    except GraphTraceBusy:
        return Trace.THROTTLED, TRACE_NOTES[Trace.THROTTLED]
    except GraphTraceNotPermitted as exc:
        result = Trace.NO_SERVICE_PRINCIPAL if exc.status == 401 else Trace.NOT_CONSENTED
        return result, TRACE_NOTES[result]
    except (GraphTraceError, EmailDeliveryError) as exc:
        return Trace.ERROR, text.scrub(str(exc))
    # Granted now: a sync waiting out an earlier "not permitted" may run again.
    trace_state.clear_not_permitted(sender)
    return Trace.AVAILABLE, "Microsoft answered a one-hour Message Trace query for the From address."


def run_and_record(config, *, checked_by=None) -> tuple[PermissionReport, MicrosoftGraphPermissionCheck]:
    """Check *config*'s permissions, store the run and keep only the latest ones."""
    report = check_permissions(config)
    check = MicrosoftGraphPermissionCheck.objects.create(
        config=config,
        certificate_sha1=report.certificate_sha1,
        token_ok=report.token_ok,
        token_error=report.token_error[:500],
        granted_roles=None if report.granted_roles is None else list(report.granted_roles),
        extra_roles=list(report.extra_roles),
        trace_result=report.trace_result,
        trace_note=report.trace_note[:500],
        checked_by=checked_by if getattr(checked_by, "pk", None) else None,
    )
    MicrosoftGraphPermissionCheck.prune(config)
    logger.info(
        "graph_permission_check token_ok=%s roles=%s extra=%s trace=%s sha1=%s config=%s",
        report.token_ok,
        ",".join(report.granted_roles) if report.granted_roles is not None else "unreadable",
        ",".join(report.extra_roles) or "-",
        report.trace_result,
        report.certificate_sha1 or "-",
        config.pk,
    )
    if check.checked_by_id:
        LogEntry.objects.log_actions(
            user_id=check.checked_by_id,
            queryset=[config],
            action_flag=CHANGE,
            change_message=f"Checked the Microsoft Graph permissions. Message Trace: {check.get_trace_result_display()}.",
            single_object=True,
        )
    return report, check
