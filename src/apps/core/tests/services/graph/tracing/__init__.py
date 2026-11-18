"""Fixtures for the Message Trace tests: a fake Microsoft behind ``graph.transport.request`` (so the real transport
and its allow-list run), trace rows and pages, and the site sending through Graph with Message Trace switched on."""

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.services.email.graph import clear_access_token_cache, transport
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.core.tests.services.graph.provider.test_email_graph import token_response
from apps.core.tests.services.graph_access.helpers import token_with_roles

SENDER = "i2g@ucmerced.edu"
REQUEST = "apps.core.services.email.graph.transport.request"
TRACES = "/v1.0/admin/exchange/tracing/messageTraces"
NEXT = f"https://graph.microsoft.com{TRACES}?$filter=whatever&$top=1000&$skiptoken="
TRACE_ROLE = "ExchangeMessageTrace.Read.All"
TRACE_ROLES = ("Mail.ReadWrite", "Mail.Send", TRACE_ROLE)
# Values only a trace row holds: they must never reach a log line.
PRIVATE = ("person@example.com", "203.0.113.9", "Secret subject")


def stamp(moment) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def trace_row(message_id="<m1@ucmerced.edu>", recipient="person@example.com", status="delivered", **values):
    received = values.pop("received", None) or timezone.now() - timedelta(hours=1)
    return {
        "id": str(uuid.uuid4()),
        "messageId": message_id,
        "recipientAddress": recipient,
        "senderAddress": SENDER,
        "subject": values.pop("subject", "Hello"),
        "status": status,
        "receivedDateTime": stamp(received),
        "fromIP": "203.0.113.9",
        "toIP": "198.51.100.7",
        "size": 2048,
        **values,
    }


def trace_page(rows=(), *, skiptoken=None, status=200, headers=None, truncated=False, body=None):
    data = {"value": list(rows)}
    if skiptoken is not None:
        data["@odata.nextLink"] = f"{NEXT}{skiptoken}"
    payload = json.dumps(data).encode() if body is None else body
    return HttpResponse(status, headers or {}, payload, truncated=truncated)


class FakeMicrosoft:
    """Answers the token request (a token claiming ``roles``) and each trace request with the next page in ``pages``
    (the last one repeats); records every request."""

    def __init__(self, roles=TRACE_ROLES):
        self.token = token_response(token=token_with_roles(roles))
        self.pages = [trace_page()]
        self.requests = []

    def __call__(self, method, host, path, body, headers, *, timeout, max_bytes, user_agent):
        self.requests.append({"method": method, "host": host, "path": path, "max_bytes": max_bytes})
        if host == transport.AUTHORITY_HOST:
            return self.token
        return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]

    @property
    def traces(self) -> list[dict]:
        return [request for request in self.requests if request["host"] == transport.GRAPH_HOST]

    @property
    def tokens(self) -> int:
        return sum(1 for request in self.requests if request["host"] == transport.AUTHORITY_HOST)


class TraceSetupMixin:
    """Graph configured for ``SENDER`` with Message Trace on, the From address ``SENDER``, a fake Microsoft."""

    message_trace = True

    def setUp(self):
        super().setUp()
        cache.clear()
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.config = create_graph_config(
            scope=(SENDER,), is_active=True, mailbox=SENDER, message_trace_enabled=self.message_trace
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)
        self.microsoft = FakeMicrosoft()
        patcher = patch(REQUEST, side_effect=self.microsoft)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sent(self, hours_ago=1.0, **values):
        """An accepted Graph email from ``SENDER``, *hours_ago* hours ago."""
        when = timezone.now() - timedelta(hours=hours_ago)
        values.setdefault("internet_message_id", "<m1@ucmerced.edu>")
        values.setdefault("mailbox", SENDER)
        return make_email(accepted_at=when, last_attempt_at=when, **values)
