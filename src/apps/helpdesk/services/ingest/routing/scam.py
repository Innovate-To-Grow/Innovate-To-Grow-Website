"""What the helpdesk makes of the Mail app's rule-based scam checks (``analyze_email``; never the optional Bedrock
second opinion, so no message text leaves the site).

- What is scored: the sender's own words. A message that answers a person's ticket (``replies.answers_a_person``) is
  scored without the text it quotes (staff's reply, "your account has been unlocked: click here", reads like a phish)
  and without a reply's subject (the ticket's own, judged when it arrived). Microsoft Safe Links are unwrapped, so the
  link checks see where a link really goes.
- A sender or link domain imitating one of the site's own (``ucrnerced.edu``) counts as one imitating a brand does.
- Spam: a high score, unless the sender proved their domain (DMARC, Exchange's composite authentication, or Exchange
  marking the mail internal to the organisation) or the message answers a person's ticket: then only a phishing
  signal keeps it spam (a look-alike or punycode domain, a link that hides where it goes, hidden HTML, failed
  authentication), and otherwise it is flagged suspicious. A missing display name, a brand's name in a person's name
  (Chase Lee) or a Reply-To elsewhere (a web form) are no phishing signals. A medium score flags the message
  suspicious, unless the sender proved their domain and nothing but the words scored (a person asking how to reset a
  password).
- The reasons kept for staff: the five that weigh most, phishing signals first, in the checks' order.
"""

import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from apps.core.services.email.inbound.classification.autoreply import own_subject, own_text
from apps.core.services.email.inbound.classification.headers import first
from apps.mail.services.scam_detector import (
    BRAND_NAMES,
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    analyze_email,
    check_authentication,
    check_links,
)
from apps.mail.services.scam_detector.checks import body_text
from apps.mail.services.scam_detector.domains import (
    brand_lookalike,
    email_domain,
    registrable_domain,
    suspicious_idn_reason,
)
from apps.mail.services.scam_detector.links import extract_links, extract_text_urls
from apps.mail.services.scam_detector.structure import html_hidden_reasons

from ..reading.message import ParsedMessage

MAX_REASONS = 5
# Methods whose "pass" in Authentication-Results proves the From domain.
PROVEN_BY = ("dmarc", "compauth")
INTERNAL = "internal"
_SAFE_LINK_RE = re.compile(r"https://[a-z0-9.-]*safelinks\.protection\.outlook\.com/\?[^\s\"'<>]+", re.IGNORECASE)
# The link check's only finding that says nothing about where a link goes (a newsletter links to many domains).
_SPREAD = "Links point to "


@dataclass(frozen=True)
class Judgement:
    level: str = ""
    reasons: tuple[str, ...] = ()

    @property
    def spam(self) -> bool:
        return self.level == "high"


def internal(headers) -> bool:
    """Exchange marks mail sent inside the organisation (it strips the header from mail arriving from outside)."""
    return first(headers, "x-ms-exchange-organization-authas").strip().lower() == INTERNAL


def authenticated(auth: dict) -> bool:
    auth = auth or {}
    passed = any(str(auth.get(method, "")).lower() == "pass" for method in PROVEN_BY)
    return passed or str(auth.get("authas", "")).lower() == INTERNAL


def _unwrapped(match) -> str:
    query = parse_qs(urlsplit(html_lib.unescape(match.group(0))).query)
    return (query.get("url") or [match.group(0)])[0].replace('"', "%22")


def unwrap_safe_links(value: str) -> str:
    return _SAFE_LINK_RE.sub(_unwrapped, value or "")


def scam_input(parsed: ParsedMessage, *, answered: bool) -> dict:
    text, html, subject = parsed.text[:65536], unwrap_safe_links(parsed.html[:262144]), parsed.subject
    if answered:
        # What the answer adds: neither the quote of the reply it answers nor the thread's subject.
        text, html, subject = own_text(text or body_text({"html": html})), "", own_subject(subject)
    headers = parsed.headers
    return {
        "from_email": parsed.from_address,
        "from_name": parsed.from_name,
        "subject": subject,
        "text": unwrap_safe_links(text),
        "html": html,
        "reply_to": parsed.reply_to,
        "return_path": (headers.get("return-path") or [""])[0].strip().strip("<>").lower()[:254],
        "authentication_results": " ".join(headers.get("authentication-results", ()))[:8192],
    }


def own_labels(own) -> list[str]:
    """The brand-like label of each of the site's own domains (``ucmerced`` for i2g@ucmerced.edu)."""
    labels = (registrable_domain(email_domain(address)).partition(".")[0] for address in own)
    return list(dict.fromkeys(label for label in labels if label.isalnum()))


def own_lookalikes(data: dict, labels: list[str]) -> list[tuple[int, str]]:
    """A sender or link domain imitating one of the site's own (each 3 points, like a brand look-alike)."""
    if not labels:
        return []
    links = [*extract_links(data["html"]), *extract_text_urls(body_text(data))]
    domains = [email_domain(data["from_email"]), *(link["href_domain"] for link in links)]
    reasons = dict.fromkeys(reason for domain in domains if domain and (reason := brand_lookalike(domain, labels)))
    return [(3, reason) for reason in reasons]


def phishing_signals(data: dict) -> list[tuple[int, str]]:
    """The checks that point at phishing whatever the words say (see the module docstring)."""
    domain = email_domain(data["from_email"])
    sender = [(3, reason) for reason in (suspicious_idn_reason(domain), brand_lookalike(domain, BRAND_NAMES)) if reason]
    links = [(score, reason) for score, reason in check_links(data, BRAND_NAMES) if not reason.startswith(_SPREAD)]
    hidden = [(2, reason) for reason in html_hidden_reasons(data["html"])] if data["html"] else []
    return [*sender, *links, *hidden, *check_authentication(data)]


def _level(score: int, level: str) -> str:
    if score >= HIGH_THRESHOLD:
        return "high"
    return "medium" if score >= MEDIUM_THRESHOLD else level


def judge(parsed: ParsedMessage, auth: dict, own, *, answered: bool) -> Judgement:
    data = scam_input(parsed, answered=answered)
    analysis = analyze_email(data)
    extra = own_lookalikes(data, own_labels(own))
    level = str(analysis.get("risk_level") or "")
    if extra:
        level = _level(int(analysis.get("score") or 0) + sum(score for score, _reason in extra), level)
    phishing = [*extra, *phishing_signals(data)]
    warns = sum(score for score, _reason in phishing) >= MEDIUM_THRESHOLD
    proven = authenticated(auth)
    if level == "high" and (proven or answered) and not warns:
        level = "medium"  # a person's message, flagged suspicious
    elif level == "medium" and proven and not phishing:
        level = "low"  # a proven sender's words alone
    if level not in ("medium", "high"):
        return Judgement(level)
    return Judgement(level, _top_reasons(analysis, extra, {reason for _score, reason in phishing}))


def _top_reasons(analysis: dict, extra, decisive: set) -> tuple[str, ...]:
    ordered = [*(reason for _score, reason in extra), *(str(reason) for reason in analysis.get("reasons") or ())]
    weight = {item.get("reason"): item.get("score", 0) for item in analysis.get("findings") or ()}
    weight.update({reason: score for score, reason in extra})
    ranked = sorted(range(len(ordered)), key=lambda i: (ordered[i] not in decisive, -weight.get(ordered[i], 0), i))
    return tuple(ordered[i] for i in sorted(ranked[:MAX_REASONS]))
