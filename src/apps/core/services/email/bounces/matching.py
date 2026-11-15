"""Matching a bounced recipient to the outgoing email it reports on, without guessing.

1. Exact: the report quotes the original Message-ID, and an email the site sent carries it (the MIME form of
   Microsoft Graph's sendMail, used for every email that may keep a Sent Items copy).
2. Inferred: no Message-ID can match (the JSON form, used for emails that carry a credential, gives the site no
   Message-ID), and exactly one email the site sent to the same recipient, with the same subject, in the window
   before the report arrived qualifies. An email whose Message-ID the site knows is never inferred for a report that
   quotes another Message-ID: that report is about some other message (one staff sent from Outlook, say).

Anything else stays unmatched, and the dashboard lists it as such.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings

from apps.core.models import EmailBounce, EmailCategory, OutboundEmail

from ..telemetry import text

MatchMethod = EmailBounce.MatchMethod
# Allowance for the clock difference between the site and Exchange (the report's received time).
_CLOCK_SKEW = timedelta(minutes=10)


@dataclass(frozen=True)
class Match:
    email: OutboundEmail | None
    method: str
    note: str = ""


def match(*, recipient: str, original_message_id: str, original_subject: str, received_at: datetime) -> Match:
    if original_message_id:
        email = OutboundEmail.objects.filter(internet_message_id=original_message_id).order_by("-created_at").first()
        if email is not None:
            return Match(email, MatchMethod.MESSAGE_ID, "The report quotes this email's Message-ID.")
    if not recipient:
        return Match(None, MatchMethod.UNMATCHED, "The report names no recipient.")
    digest = text.subject_digest(original_subject)
    if not digest:
        return Match(None, MatchMethod.UNMATCHED, "The report gives neither a known Message-ID nor the subject.")
    window = timedelta(hours=settings.EMAIL_MONITORING["bounce_match_window_hours"])
    candidates = OutboundEmail.objects.filter(
        recipient=recipient,
        subject_digest=digest,
        status__in=[OutboundEmail.Status.ACCEPTED, OutboundEmail.Status.UNCERTAIN],
        last_attempt_at__gte=received_at - window,
        last_attempt_at__lte=received_at + _CLOCK_SKEW,
    ).exclude(category=EmailCategory.ACCESS_CHECK)
    if original_message_id:
        candidates = candidates.filter(internet_message_id="")
    found = list(candidates.order_by("-last_attempt_at")[:2])
    if len(found) == 1:
        return Match(
            found[0], MatchMethod.RECIPIENT, "The only email to this recipient with this subject in the window."
        )
    if found:
        return Match(None, MatchMethod.UNMATCHED, "Several emails to this recipient share the subject; not matched.")
    return Match(None, MatchMethod.UNMATCHED, "No email the site sent matches the report.")
