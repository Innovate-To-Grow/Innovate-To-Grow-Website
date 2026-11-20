"""What the helpdesk makes of the Mail app's rule-based scam checks (their deterministic rules only: never the
optional Bedrock second opinion, so no message text leaves the site).

- The words: a message that answers a person's ticket (``replies.answers_a_person``) is judged on what its sender
  wrote, without what it quotes ("> …" lines, the "On … wrote:" or Outlook header block and what follows it, an HTML
  quote block) and without a reply's subject (the ticket's own): staff's reply ("your account has been unlocked: click
  here …") reads like a phish.
- The phishing signals look at the whole message, quote included (staff's replies carry none): a look-alike or
  punycode sender or link domain (one imitating the site's own, ``ucrnerced.edu``, too); a link that hides where it
  goes (text naming another domain, a raw IP, a shortener); hidden HTML; failed DMARC or SPF. Link protection
  (Microsoft Safe Links, Proofpoint URL Defense) is unwrapped first, so a link is judged by where it goes.
- Spam: a high score, unless the sender proved their domain (DMARC, Exchange's composite authentication, or Exchange
  marking the mail internal to the organisation) or the message answers a person's ticket: then only a phishing
  signal keeps it spam (any of them; an SPF soft fail or a DKIM failure alone does not), and otherwise it is flagged
  suspicious. Such a sender is judged by its domain, not by its name (Chase Lee) or by where it asks replies to go (a
  web form's Reply-To). A medium score flags a message suspicious, unless the sender proved their domain and nothing
  but its words scored (a person asking how to reset a password).
- The reasons kept for staff: the five that weigh most, phishing signals first, in the checks' order.
"""

import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from apps.core.services.email.inbound.classification.autoreply import own_subject, own_text
from apps.core.services.email.inbound.classification.headers import first
from apps.mail.services.scam_detector import (
    BRAND_NAMES,
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    check_address_alignment,
    check_authentication,
    check_body,
    check_links,
    check_sender,
    check_structure,
    check_subject,
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
PROVEN_BY = ("dmarc", "compauth")  # methods whose "pass" in Authentication-Results proves the From domain
INTERNAL = "internal"
DECISIVE = 2  # what a phishing signal weighs at least to keep a trusted sender's high score spam
_WRAPPED_RE = re.compile(
    r"https://(?:[a-z0-9.-]*safelinks\.protection\.outlook\.com/\?|urldefense\.proofpoint\.com/v2/url\?|"
    r"urldefense\.com/v3/__)[^\s\"'<>]+",
    re.IGNORECASE,
)
_QUOTED_LINE_RE = re.compile(r"^[ \t]*>[^\n]*\n?", re.MULTILINE)
_SPREAD = "Links point to "  # the link check's only finding that says nothing about where a link goes


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
    wrapped = html_lib.unescape(match.group(0))
    if "/v3/__" in wrapped:
        inner = wrapped.split("/v3/__", 1)[1].split("__;", 1)[0]
    else:
        query = parse_qs(urlsplit(wrapped).query)
        inner = (query.get("url") or query.get("u") or [""])[0]
        if "urldefense.proofpoint.com" in wrapped.lower():  # v2 writes "-3A" for ":" and "_" for "/"
            inner = re.sub(r"-([0-9A-Fa-f]{2})", lambda hit: chr(int(hit.group(1), 16)), inner.replace("_", "/"))
    return (inner or match.group(0)).replace('"', "%22")


def unwrap_links(value: str) -> str:
    return _WRAPPED_RE.sub(_unwrapped, value or "")


def _html_without_quotes(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for quote in soup.select("blockquote, .gmail_quote, .yahoo_quoted"):
        quote.decompose()
    marker = soup.select_one("#appendonsend, #divRplyFwdMsg")  # Outlook: the quoted message follows it
    if marker is not None:
        for sibling in list(marker.find_next_siblings()):
            sibling.decompose()
        marker.decompose()
    return soup.get_text("\n")


def own_words(text: str, html: str) -> str:
    """What the sender of an answer wrote: its text (or its HTML's) without the lines it quotes."""
    if not text.strip() and html:
        text = _html_without_quotes(html)
    return own_text(_QUOTED_LINE_RE.sub("", text))


def scam_input(parsed: ParsedMessage) -> dict:
    headers = parsed.headers
    return {
        "from_email": parsed.from_address,
        "from_name": parsed.from_name,
        "subject": parsed.subject,
        "text": unwrap_links(parsed.text[:65536]),
        "html": unwrap_links(parsed.html[:262144]),
        "reply_to": parsed.reply_to,
        "return_path": (headers.get("return-path") or [""])[0].strip().strip("<>").lower()[:254],
        "authentication_results": " ".join(headers.get("authentication-results", ()))[:8192],
    }


def own_labels(own) -> list[str]:
    """The brand-like label of each of the site's own domains (``ucmerced`` for i2g@ucmerced.edu)."""
    labels = (registrable_domain(email_domain(address)).partition(".")[0] for address in own)
    return list(dict.fromkeys(label for label in labels if label.isalnum()))


def _domains(data: dict) -> list[str]:
    links = [*extract_links(data["html"]), *extract_text_urls(body_text(data))]
    return [email_domain(data["from_email"]), *(link["href_domain"] for link in links)]


def findings(words: dict, full: dict, labels: list[str], *, trusted: bool) -> tuple[list, list]:
    """``(every finding, the phishing signals among them)``, in the checks' order: the words judged from ``words``,
    the rest from the whole message ``full``. A trusted sender is judged by its domain only."""
    domain = email_domain(full["from_email"])
    own = [(3, reason) for reason in dict.fromkeys(filter(None, (brand_lookalike(d, labels) for d in _domains(full))))]
    by_domain = [reason for reason in (suspicious_idn_reason(domain), brand_lookalike(domain, BRAND_NAMES)) if reason]
    sender = [(3, reason) for reason in by_domain] if trusted else check_sender(full, BRAND_NAMES)
    links, structure, failed = check_links(full, BRAND_NAMES), check_structure(full), check_authentication(full)
    hidden = set(html_hidden_reasons(full["html"])) if full["html"] else set()
    every = [*own, *sender, *check_subject(words), *check_body(words), *links, *structure, *failed]
    every += [] if trusted else check_address_alignment(full)
    phishing = [*own, *(item for item in sender if item[1] in by_domain), *failed]
    phishing += [item for item in links if not item[1].startswith(_SPREAD)] + [i for i in structure if i[1] in hidden]
    return every, phishing


def judge(parsed: ParsedMessage, auth: dict, own, *, answered: bool) -> Judgement:
    full = scam_input(parsed)
    words = full
    if answered:
        words = {**full, "subject": own_subject(full["subject"]), "text": own_words(full["text"], full["html"])}
        words["html"] = ""
    proven = authenticated(auth)
    every, phishing = findings(words, full, own_labels(own), trusted=proven or answered)
    score = sum(weight for weight, _reason in every)
    level = "high" if score >= HIGH_THRESHOLD else ("medium" if score >= MEDIUM_THRESHOLD else "low")
    if level == "high" and (proven or answered) and not any(weight >= DECISIVE for weight, _reason in phishing):
        level = "medium"  # a person's message, flagged suspicious
    elif level == "medium" and proven and not phishing:
        level = "low"  # a proven sender's words alone
    if level not in ("medium", "high"):
        return Judgement(level)
    return Judgement(level, _top_reasons(every, {reason for _weight, reason in phishing}))


def _top_reasons(every: list, decisive: set) -> tuple[str, ...]:
    ranked = sorted(range(len(every)), key=lambda i: (every[i][1] not in decisive, -every[i][0], i))
    return tuple(every[i][1] for i in sorted(ranked[:MAX_REASONS]))
