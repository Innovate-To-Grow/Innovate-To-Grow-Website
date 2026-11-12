"""Finding the email the site sent that an inbound message answers, before the message is classified.

1. **Exact:** its In-Reply-To or References name the Message-ID of an email the site sent (the MIME form of Microsoft
   Graph's sendMail, which campaigns use unless they carry a personal sign-in link).
2. **Inferred:** an email that carries a sign-in link is sent as Graph JSON, which gives the site no Message-ID, so a
   reply to it names an id the site never learned. A message that is a reply (it has In-Reply-To or References), from
   the address such an email went to, whose subject is that email's subject once its reply, automatic-reply and
   gateway tags ("RE:", "Automatic reply:", "[EXTERNAL]", …) come off, is matched to the newest one sent at most
   ``HelpdeskSettings.reply_match_window_days`` before it arrived. As for bounce reports, an email whose Message-ID the
   site knows is never inferred.

The classifier then knows the message answers the site's own mail (weak bulk signals no longer hide a person's
answer), and a left-the-organisation notice is matched to the address the site mailed. The telemetry keeps outgoing
emails for ``EMAIL_MONITORING["retention_days"]`` (180) days: a reply to older mail is not recognised.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.core.models import EmailCategory, OutboundEmail
from apps.core.services.email.inbound.rules import AUTO_REPLY_SUBJECT_RE
from apps.core.services.email.telemetry import text

from .matching import references_of
from .parse import ParsedMessage

MAX_TAGS = 10
EXACT, INFERRED = "message_id", "recipient_subject"
SENT = (OutboundEmail.Status.ACCEPTED, OutboundEmail.Status.UNCERTAIN)
# Allowance for the clock difference between the site and Exchange (the message's received time).
_CLOCK_SKEW = timedelta(minutes=10)
# A reply, forward or gateway tag at the start of a subject: "RE:", "AW:", "Fwd:", "RE[2]:", "[EXTERNAL]", "*EXT*".
_TAG_RE = re.compile(
    r"^\s*(?:(?:re|aw|sv|antw|vs|r|odp|ynt|res|fwd?|fw|wg|tr|rv|enc)\s*(?:\[\d{1,3}\])?\s*[:：]|"
    r"\[[^\]\n]{1,40}\]|\*{1,2}[^*\n]{1,40}\*{1,2})\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Replied:
    email: OutboundEmail
    method: str


def subject_stages(subject: str) -> list[str]:
    """The subject, then what is left as each leading tag comes off: any of them may be the original's (whose own
    subject may start with a bracketed tag)."""
    stages = [str(subject or "")[:998]]
    for _ in range(MAX_TAGS):
        current = stages[-1]
        shorter = AUTO_REPLY_SUBJECT_RE.sub("", current, count=1).lstrip()
        if shorter == current:
            shorter = _TAG_RE.sub("", current, count=1)
        if shorter == current or not shorter:
            break
        stages.append(shorter)
    return stages


def site_mail_replied(parsed: ParsedMessage, *, received_at: datetime, window: timedelta) -> Replied | None:
    """The email the site sent that ``parsed`` answers, and how it was found; None when it answers none."""
    references = references_of(parsed)
    if not references:
        return None
    exact = OutboundEmail.objects.filter(internet_message_id__in=references).order_by("-created_at").first()
    if exact is not None:
        return Replied(exact, EXACT)
    digests = {text.subject_digest(stage) for stage in subject_stages(parsed.subject)} - {""}
    if not parsed.from_address or not digests:
        return None
    inferred = (
        OutboundEmail.objects.filter(
            recipient=parsed.from_address,
            subject_digest__in=digests,
            internet_message_id="",
            status__in=SENT,
            last_attempt_at__gte=received_at - window,
            last_attempt_at__lte=received_at + _CLOCK_SKEW,
        )
        .exclude(category=EmailCategory.ACCESS_CHECK)
        .order_by("-last_attempt_at")
        .first()
    )
    return Replied(inferred, INFERRED) if inferred is not None else None
