"""The helpdesk's verdict on one message: ``core``'s header classifier, then the Mail app's rule-based scam score.

The header classifier decides whether a message is automated (``apps.core.services.email.inbound.classify``). It is
told first whether the message replies to an email the site sent (``replies.site_mail_replied``), so a person who
answers a campaign from a CRM or sales tool (whose mail carries bulk headers) is still a person; list mail that
replies to the site's mail (a reply sent to a whole mailing list) stays list mail, flagged ``reply_to_our_mail`` so
staff find it among the automated tickets. A message it leaves as human (which includes "uncertain") is also scored by
the scam detector's deterministic rules (``analyze_email``; never the optional Bedrock second opinion, so no message
text leaves the site): a high score makes it spam, a medium one keeps it a normal ticket flagged suspicious, as does a
message that claims the site's own address without proof.

What the inbound queue row keeps of the verdict (``Classified.result``): the email the site sent that the message
answers, how it was found and the address it went to, and, for a left-the-organisation notice, the address the notice
names instead (a hint, never verified). Bounced addresses counts those notices from it.
"""

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from apps.core.models import EmailServiceConfig, OutboundEmail
from apps.core.services.email.inbound import Evidence, Verdict, auth_summary, classify
from apps.mail.services.scam_detector import analyze_email
from apps.mail.services.suppression import normalize_address

from ...models import HelpdeskSettings
from . import replies
from .parse import ParsedMessage

SPAM = "spam"
BULK = "bulk"
REPLY_FLAG = "reply_to_our_mail"
# Hints shown on a ticket as flags (the classifier's other hints stay on the message).
FLAGGED_HINTS = frozenset({"possible_auto_reply", "possible_left_org"})


@dataclass(frozen=True)
class SiteReply:
    """The email the site sent that a message answers, how it was found (``replies``), its campaign, and the address
    it went to that the message speaks for: the sender when the email went to them, else its only recipient when the
    sender is of the same organisation (an alias, or the mailbox that answers for a departed person); "" otherwise
    (several recipients, or a third party the email was redirected to)."""

    email_id: uuid.UUID
    recipient: str = ""
    method: str = replies.EXACT
    campaign_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Classified:
    verdict: Verdict
    scam_level: str = ""
    flags: tuple[str, ...] = ()
    auth: dict = field(default_factory=dict)
    site_reply: SiteReply | None = None

    @property
    def automated(self) -> bool:
        return self.verdict.automated

    def result(self) -> dict:
        """The verdict's facts the inbound queue row keeps for other tools."""
        data = {}
        if self.site_reply is not None:
            data.update(site_mail=str(self.site_reply.email_id), site_match=self.site_reply.method)
            if self.site_reply.recipient:
                data["site_recipient"] = self.site_reply.recipient
        if self.verdict.contact:
            data.update(named_contact=self.verdict.contact, named_contact_kind=self.verdict.contact_kind)
        return data


def own_addresses(mailbox: str) -> frozenset[str]:
    """The site's own addresses: the mailbox read and the configured From address."""
    addresses = (mailbox, EmailServiceConfig.load().from_email)
    return frozenset(str(address or "").strip().lower() for address in addresses) - {""}


def _scam_input(parsed: ParsedMessage) -> dict:
    headers = parsed.headers
    return {
        "from_email": parsed.from_address,
        "from_name": parsed.from_name,
        "subject": parsed.subject,
        "text": parsed.text[:65536],
        "html": parsed.html[:262144],
        "reply_to": parsed.reply_to,
        "return_path": (headers.get("return-path") or [""])[0].strip().strip("<>").lower()[:254],
        "authentication_results": " ".join(headers.get("authentication-results", ()))[:8192],
    }


def same_organisation(first: str, second: str) -> bool:
    """Whether two addresses share a domain, or one's domain is a subdomain of the other's."""
    one, two = first.rpartition("@")[2], second.rpartition("@")[2]
    return bool(one and two) and (one == two or one.endswith(f".{two}") or two.endswith(f".{one}"))


def site_reply_of(replied: replies.Replied | None, sender: str) -> SiteReply | None:
    if replied is None:
        return None
    email: OutboundEmail = replied.email
    recipients = list(dict.fromkeys(filter(None, map(normalize_address, email.recipients or [email.recipient]))))
    sender = normalize_address(sender)
    if sender in recipients:
        recipient = sender
    else:
        only = recipients[0] if len(recipients) == 1 else ""
        recipient = only if only and same_organisation(sender, only) else ""
    return SiteReply(email.pk, recipient, replied.method, email.campaign_id)


def _verdict(parsed: ParsedMessage, own: frozenset, settings: HelpdeskSettings, replied: SiteReply | None) -> Verdict:
    evidence = Evidence(
        headers=parsed.headers,
        from_address=parsed.from_address,
        from_name=parsed.from_name,
        subject=parsed.subject,
        content_type=parsed.content_type,
        report_type=parsed.report_type,
        has_calendar=parsed.has_calendar,
        text_head=parsed.text_head(),
        replies_to_site_mail=replied is not None,
    )
    verdict = classify(
        evidence,
        own_addresses=own,
        scl_threshold=int(settings.spam_scl_threshold),
        bcl_threshold=int(settings.bulk_bcl_threshold),
    )
    if verdict.contact and replied is not None and verdict.contact == replied.recipient:
        verdict = replace(verdict, contact="", contact_kind="")  # the address the site mailed is not a new one
    return verdict


def classify_message(
    parsed: ParsedMessage, *, mailbox: str, settings: HelpdeskSettings, received_at: datetime
) -> Classified:
    window = timedelta(days=int(settings.reply_match_window_days))
    found = replies.site_mail_replied(parsed, received_at=received_at, window=window)
    replied = site_reply_of(found, parsed.from_address)
    verdict = _verdict(parsed, own_addresses(mailbox), settings, replied)
    auth = auth_summary(parsed.headers)
    if verdict.automated:
        flags = (REPLY_FLAG,) if verdict.classification == BULK and replied is not None else ()
        return Classified(verdict, flags=flags, auth=auth, site_reply=replied)
    flags = [hint for hint in verdict.hints if hint in FLAGGED_HINTS]
    scam_level = str(analyze_email(_scam_input(parsed)).get("risk_level") or "")
    if scam_level == "high":
        spam = Verdict(SPAM, "scam_score", ("scam_score_high",), verdict.hints)
        return Classified(spam, scam_level, auth=auth, site_reply=replied)
    if scam_level == "medium" or "claims_own_address" in verdict.hints:
        flags.append("suspicious")
    return Classified(verdict, scam_level, tuple(dict.fromkeys(flags)), auth, replied)
