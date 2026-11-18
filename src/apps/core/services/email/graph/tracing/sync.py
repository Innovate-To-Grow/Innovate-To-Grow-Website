"""One Message Trace sync of the site's sender: the gates, the lease, the token-roles pre-check and the backoff.

The sync runs only while the active Graph config's ``message_trace_enabled`` is on, Graph is configured, the From
address may send in the mailbox scope and the sender's backoff has passed. Before any trace request it reads the
token's ``roles`` claim; a cached token without ``ExchangeMessageTrace.Read.All`` is replaced by a newly issued one
first (it may predate the grant). Only when a just-issued token lacks the role is no request made, and the sync waits
six hours; a token carrying it ends an earlier "not permitted" even when there is nothing to trace. The claim is only
ever used to skip a request that would fail, never to grant anything: Microsoft decides on the real call. Microsoft's
401/403 also waits six hours; a throttle waits Retry-After (``state.throttle_delay``). Nothing here touches the
delivery-rate lanes of sending (``reader``). The window length the last run settled on (``windows``) is carried over.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import MESSAGE_TRACE_ROLE

from ...sending.exceptions import EmailDeliveryError
from ...telemetry import text
from ..access_check.roles import token_roles
from ..identity.access import SEND
from . import limits, state
from .reader import GraphTraceBusy, GraphTraceError, GraphTraceNotPermitted, GraphTraceReader
from .windows import MAX_WINDOW, TraceRun

logger = logging.getLogger(__name__)
Permission = state.Permission
ROLE_MISSING = (
    f"The access token does not carry {MESSAGE_TRACE_ROLE}, so no Message Trace request was made; it is checked "
    "again in six hours."
)


@dataclass
class TraceOutcome:
    status: str  # ok, partial, busy, not_permitted, failed, disabled, inactive, waiting or locked
    sender: str = ""
    stats: dict = field(default_factory=dict)
    error: str = ""
    retry_after: int | None = None


def enabled() -> bool:
    """Whether the active Graph config has Message Trace switched on (it is off by default)."""
    return bool(MicrosoftGraphProviderConfig.load().message_trace_enabled)


def sync_delivery(*, now: datetime | None = None) -> TraceOutcome:
    graph = MicrosoftGraphProviderConfig.load()
    if not graph.message_trace_enabled:
        return TraceOutcome("disabled")
    if not graph.is_configured:
        return TraceOutcome("inactive", error="Microsoft Graph is not configured.")
    from_email = EmailServiceConfig.load().from_email
    sender = text.address(from_email)
    if not sender or not graph.allows(sender, SEND):
        problem = "The Microsoft Graph mailbox scope does not let the From address send, so it is not traced."
        if sender:
            state.record_problem(sender, problem)
        return TraceOutcome("inactive", sender, error=problem)
    now = now or timezone.now()
    current = state.state_for(sender)
    if current.next_run_after is not None and current.next_run_after > now:
        return TraceOutcome("waiting", sender)
    budget = limits.max_requests_per_run()
    try:
        reader = GraphTraceReader(graph, sender)
    except EmailDeliveryError as exc:
        return TraceOutcome("inactive", sender, error=str(exc))
    token = state.acquire_lease(sender, now, (budget + 1) * reader.timeout * 2)
    if token is None:
        return TraceOutcome("locked", sender)
    current.refresh_from_db(fields=["last_run_stats"])
    last = current.last_run_stats or {}
    throttles = int(last.get("throttles", 0) or 0)
    minutes = int(last.get("window_minutes", 0) or 0)
    span = timedelta(minutes=minutes) if minutes > 0 else MAX_WINDOW
    run = TraceRun(reader, graph.sender_mailbox(from_email), now, budget, span=span)
    return _run(sender, token, run, throttles)


def trace_roles(reader: GraphTraceReader) -> tuple[str, ...] | None:
    """The token's roles; when a cached token lacks the trace role, those of a newly issued one (a token's roles are
    fixed when it is issued, and this worker's cache is not the one "Check permissions" refreshed)."""
    token, issued = reader.access_token()
    roles = token_roles(token)
    if roles is not None and MESSAGE_TRACE_ROLE not in roles and not issued:
        roles = token_roles(reader.access_token(fresh=True)[0])
    return roles


def _run(sender: str, token, run: TraceRun, throttles: int) -> TraceOutcome:
    stats = run.stats
    roles = None
    try:
        roles = trace_roles(run.reader)
        if roles is not None and MESSAGE_TRACE_ROLE not in roles:
            return _not_permitted(sender, token, stats, ROLE_MISSING)
        status = run.execute()
    except GraphTraceBusy as exc:
        delay = state.throttle_delay(throttles, exc.retry_after)
        state.finish(sender, token, stats={**stats, "throttles": throttles + 1}, delay=delay)
        return TraceOutcome("busy", sender, stats, retry_after=delay)
    except GraphTraceNotPermitted as exc:
        return _not_permitted(sender, token, stats, str(exc))
    except GraphTraceError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a sync failure is recorded for the dashboard, never raised.
        logger.error("Message Trace sync failed with an unexpected %s", type(exc).__name__)
        error = f"Unexpected {type(exc).__name__}"
    else:
        # An answered request proves the permission; a token carrying the role at least ends "not permitted".
        permission = Permission.OK if stats["requests"] else (Permission.UNKNOWN if roles is not None else None)
        state.finish(sender, token, stats=stats, permission=permission, succeeded=True)
        return TraceOutcome(status, sender, stats)
    state.finish(sender, token, stats=stats, error=error)
    return TraceOutcome("failed", sender, stats, error=error)


def _not_permitted(sender: str, token, stats: dict, problem: str) -> TraceOutcome:
    delay = state.NOT_PERMITTED_BACKOFF_SECONDS
    state.finish(sender, token, stats=stats, error=problem, delay=delay, permission=Permission.NOT_PERMITTED)
    return TraceOutcome("not_permitted", sender, stats, error=problem, retry_after=delay)
