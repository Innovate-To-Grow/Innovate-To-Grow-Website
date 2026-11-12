"""The helpdesk's verdict on one message: ``core``'s header classifier, then the Mail app's rule-based scam score.

The header classifier decides whether a message is automated (``apps.core.services.email.inbound.classify``). A
message it leaves as human (which includes "uncertain") is also scored by the scam detector's deterministic rules
(``analyze_email``; never the optional Bedrock second opinion, so no message text leaves the site): a high score makes
it spam, a medium one keeps it a normal ticket flagged suspicious, as does a message that claims the site's own
address without proof.
"""

from dataclasses import dataclass, field

from apps.core.models import EmailServiceConfig
from apps.core.services.email.inbound import Evidence, Verdict, auth_summary, classify
from apps.mail.services.scam_detector import analyze_email

from ...models import HelpdeskSettings
from .parse import ParsedMessage

SPAM = "spam"
# Hints shown on a ticket as flags (the classifier's other hints stay on the message).
FLAGGED_HINTS = frozenset({"possible_auto_reply", "possible_left_org"})


@dataclass(frozen=True)
class Classified:
    verdict: Verdict
    scam_level: str = ""
    flags: tuple[str, ...] = ()
    auth: dict = field(default_factory=dict)

    @property
    def automated(self) -> bool:
        return self.verdict.automated


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


def classify_message(parsed: ParsedMessage, *, mailbox: str, settings: HelpdeskSettings) -> Classified:
    own = own_addresses(mailbox)
    evidence = Evidence(
        headers=parsed.headers,
        from_address=parsed.from_address,
        from_name=parsed.from_name,
        subject=parsed.subject,
        content_type=parsed.content_type,
        report_type=parsed.report_type,
        has_calendar=parsed.has_calendar,
        text_head=parsed.text_head(),
    )
    verdict = classify(evidence, own_addresses=own, scl_threshold=int(settings.spam_scl_threshold))
    auth = auth_summary(parsed.headers)
    if verdict.automated:
        return Classified(verdict, auth=auth)
    flags = [hint for hint in verdict.hints if hint in FLAGGED_HINTS]
    scam_level = str(analyze_email(_scam_input(parsed)).get("risk_level") or "")
    if scam_level == "high":
        spam = Verdict(SPAM, "scam_score", ("scam_score_high",), verdict.hints)
        return Classified(spam, scam_level, auth=auth)
    if scam_level == "medium" or "claims_own_address" in verdict.hints:
        flags.append("suspicious")
    return Classified(verdict, scam_level, tuple(dict.fromkeys(flags)), auth)
