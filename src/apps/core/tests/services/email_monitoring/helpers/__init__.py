"""Shared fixtures for the email monitoring tests: a Graph sending setup (the real facade and provider, with
``transport.post`` replaced by ``FakeGraph``) and factories for telemetry and bounce rows."""

import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.core.models import EmailBounce, EmailCategory, EmailServiceConfig, OutboundEmail, OutboundEmailAttempt
from apps.core.services.email import EmailMessage, deliver_email, email_tracking
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.services.email.telemetry import text
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.delivery_rates.helpers import FakeClock
from apps.core.tests.services.test_email_graph import GraphFixtureMixin

SENDER = "i2g@ucmerced.edu"
REQUEST_ID = "8a1b2c3d-1111-2222-3333-444455556666"
# Free text in a Microsoft error body: it must never be stored by the telemetry.
BODY_TEXT = "free-text-from-microsoft-that-must-not-be-stored"


def monitoring_settings(**changes):
    """``override_settings`` for a few ``EMAIL_MONITORING`` values, the rest unchanged."""
    return override_settings(EMAIL_MONITORING={**settings.EMAIL_MONITORING, **changes})


def graph_error(status, code="", *, inner="", headers=None):
    error = {"code": code, "message": BODY_TEXT}
    if inner:
        error["innerError"] = {"code": inner}
    body = json.dumps({"error": error}).encode() if code else b""
    return HttpResponse(status, {"request-id": REQUEST_ID, **(headers or {})}, body)


def accepted(headers=None):
    return HttpResponse(202, {"request-id": REQUEST_ID, **(headers or {})}, b"")


class GraphSendingMixin(GraphFixtureMixin):
    """The site sending through Microsoft Graph as ``SENDER``: active configs, a fresh token cache, fake transport."""

    def setUp(self):
        super().setUp()
        self.clock = FakeClock(timezone.now()).install(self)
        create_graph_config(scope=(SENDER,), name="Graph", is_active=True, mailbox=SENDER)
        self.service_config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="graph", from_email=SENDER, from_name="Innovate to Grow"
        )

    def send(self, message=None, **tracking):
        message = message or EmailMessage(subject="Hello", to=("person@example.com",), html_body="<p>Hi</p>")
        with email_tracking(**tracking):
            return deliver_email(message, config=self.service_config)


def make_email(**values) -> OutboundEmail:
    """An outgoing email row as the telemetry would have saved it (API accepted unless told otherwise)."""
    now = timezone.now()
    subject = values.pop("subject", "Hello")
    recipient = values.pop("recipient", "person@example.com")
    status = values.pop("status", OutboundEmail.Status.ACCEPTED)
    defaults = {
        "category": EmailCategory.CAMPAIGN,
        "provider": "graph",
        "recipient": recipient,
        "recipients": [recipient],
        "recipient_count": 1,
        "subject": subject,
        "subject_digest": text.subject_digest(subject),
        "status": status,
        "delivery_status": (
            OutboundEmail.DeliveryStatus.UNKNOWN
            if status == OutboundEmail.Status.ACCEPTED
            else OutboundEmail.DeliveryStatus.NOT_APPLICABLE
        ),
        "attempt_count": 1,
        "first_attempt_at": now,
        "last_attempt_at": now,
        "accepted_at": now if status == OutboundEmail.Status.ACCEPTED else None,
    }
    created_at = values.pop("created_at", None)
    email = OutboundEmail.objects.create(**{**defaults, **values})
    if created_at is not None:
        OutboundEmail.objects.filter(pk=email.pk).update(created_at=created_at)
        email.refresh_from_db()
    return email


def make_attempt(email, number=1, **values) -> OutboundEmailAttempt:
    defaults = {"provider": "graph", "operation": "send_mail", "outcome": "accepted", "http_status": 202}
    return OutboundEmailAttempt.objects.create(email=email, attempt_number=number, **{**defaults, **values})


# The category a test's coarse classification stands for, when the test names none.
CATEGORY_OF = {
    "hard": EmailBounce.Category.HARD,
    "soft": EmailBounce.Category.TRANSIENT,
    "rejected": EmailBounce.Category.POLICY_REJECTED,
    "delayed": EmailBounce.Category.DELAYED,
    "unknown": EmailBounce.Category.UNKNOWN,
}


def make_bounce(**values) -> EmailBounce:
    """A stored bounce report; its category follows its classification unless given (pass ``category=""`` for one
    the previous release saved)."""
    now = timezone.now()
    defaults = {
        "dedupe_key": values.pop("dedupe_key", None) or uuid.uuid4().hex,
        "mailbox": SENDER,
        "ndr_graph_id": "AAMkAD-ndr",
        "received_at": now,
        "recipient": "person@example.com",
        "classification": EmailBounce.Classification.HARD,
        "status_code": "5.1.1",
    }
    merged = {**defaults, **values}
    merged.setdefault("category", CATEGORY_OF.get(merged["classification"], EmailBounce.Category.UNKNOWN))
    return EmailBounce.objects.create(**merged)


def minutes_ago(minutes: int):
    return timezone.now() - timedelta(minutes=minutes)
