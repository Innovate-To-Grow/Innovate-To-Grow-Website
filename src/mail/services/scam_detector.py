"""Rule-based scam/fraud email detection heuristics."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Scoring thresholds
# ---------------------------------------------------------------------------
MEDIUM_THRESHOLD = 3
HIGH_THRESHOLD = 7

# ---------------------------------------------------------------------------
# Keyword / pattern lists
# ---------------------------------------------------------------------------

URGENCY_SUBJECT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\burgent\b",
        r"\bact now\b",
        r"\bimmediate(ly)?\b",
        r"\bsuspend(ed)?\b",
        r"\bverif(y|ication)\b",
        r"\bconfirm your\b",
        r"\baccount.{0,15}(clos|lock|restrict|limit)",
        r"\bprize\b",
        r"\bwinner\b",
        r"\bwon\b",
        r"\blotter(y|ies)\b",
        r"\binheritance\b",
        r"\bunclaimed\b",
        r"\bfinal (notice|warning)\b",
        r"\baction required\b",
        r"\bexpir(e[sd]?|ing|ation)\b",
    ]
]

BODY_URGENCY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bclick here\b",
        r"\bact (now|immediately)\b",
        r"\blimited time\b",
        r"\bdo not ignore\b",
        r"\bfailure to (respond|comply|verify)",
        r"\byour account (has been|will be|is)\s",
        r"\bwithin \d+ (hour|day|business day)",
        r"\bimmediately\b",
    ]
]

PERSONAL_INFO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(social security|ssn)\b",
        r"\bpassword\b",
        r"\bcredit card\b",
        r"\bbank account\b",
        r"\bpin (number|code)\b",
        r"\bdate of birth\b",
        r"\btax(payer)? id\b",
        r"\brouting number\b",
        r"\baccount number\b",
        r"\bwire transfer\b",
    ]
]

GENERIC_GREETING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bdear (customer|user|member|account holder|valued|sir|madam|client)\b",
        r"\bdear friend\b",
        r"\bhello dear\b",
    ]
]

MONEY_PATTERN = re.compile(
    r"(?:\$|USD|EUR|GBP|£|€)\s?[\d,]{4,}",
    re.IGNORECASE,
)

FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "aol.com",
        "mail.com",
        "protonmail.com",
        "yandex.com",
        "zoho.com",
        "icloud.com",
        "gmx.com",
        "live.com",
    }
)

BRAND_KEYWORDS_IN_NAME = re.compile(
    r"\b(amazon|paypal|apple|microsoft|google|netflix|bank|wells fargo"
    r"|chase|citibank|hsbc|irs|fedex|ups|dhl|usps)\b",
    re.IGNORECASE,
)

URL_SHORTENERS = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "goo.gl",
        "t.co",
        "ow.ly",
        "is.gd",
        "buff.ly",
        "rebrand.ly",
        "shorturl.at",
        "tiny.cc",
        "cutt.ly",
    }
)

IP_URL_PATTERN = re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------


def _check_sender(msg: dict[str, Any]) -> list[tuple[int, str]]:
    """Analyse sender for suspicious patterns. Returns (score, reason) pairs."""
    findings: list[tuple[int, str]] = []
    from_name = msg.get("from_name", "")
    from_email = msg.get("from_email", "")

    if not from_name:
        findings.append((1, "Sender has no display name"))

    email_domain = from_email.rsplit("@", 1)[-1].lower() if "@" in from_email else ""

    if from_name and email_domain:
        brand_match = BRAND_KEYWORDS_IN_NAME.search(from_name)
        if brand_match:
            brand = brand_match.group(1).lower()
            if brand not in email_domain:
                findings.append(
                    (3, f'Display name mentions "{brand_match.group(1)}" but email domain is {email_domain}')
                )

    if from_name and email_domain in FREEMAIL_DOMAINS:
        if BRAND_KEYWORDS_IN_NAME.search(from_name):
            findings.append((2, f"Claims to be a known brand but uses freemail domain ({email_domain})"))

    return findings


def _check_subject(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    subject = msg.get("subject", "")
    hits = [p.pattern for p in URGENCY_SUBJECT_PATTERNS if p.search(subject)]
    if hits:
        findings.append(
            (min(len(hits) + 1, 4), f"Subject contains urgency/scam language ({len(hits)} pattern(s) matched)")
        )
    if subject.isupper() and len(subject) > 10:
        findings.append((1, "Subject is written entirely in UPPERCASE"))
    return findings


def _get_body_text(msg: dict[str, Any]) -> str:
    """Extract plain text from the message for body analysis."""
    text = msg.get("text", "") or ""
    if text.strip():
        return text
    html = msg.get("html", "") or ""
    if html:
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return ""


def _check_body(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    body = _get_body_text(msg)
    if not body:
        return findings

    urgency_hits = sum(1 for p in BODY_URGENCY_PATTERNS if p.search(body))
    if urgency_hits >= 2:
        findings.append((min(urgency_hits, 4), f"Body contains urgency/pressure language ({urgency_hits} pattern(s))"))
    elif urgency_hits == 1:
        findings.append((1, "Body contains urgency/pressure language"))

    info_hits = [p.pattern for p in PERSONAL_INFO_PATTERNS if p.search(body)]
    if info_hits:
        findings.append(
            (min(len(info_hits) + 2, 5), f"Body requests personal/financial information ({len(info_hits)} type(s))")
        )

    if GENERIC_GREETING_PATTERNS and any(p.search(body) for p in GENERIC_GREETING_PATTERNS):
        findings.append((1, 'Uses generic greeting (e.g. "Dear Customer")'))

    money_matches = MONEY_PATTERN.findall(body)
    if len(money_matches) >= 2:
        findings.append((2, f"Body mentions large monetary amounts ({len(money_matches)} occurrence(s))"))
    elif money_matches:
        findings.append((1, "Body mentions a monetary amount"))

    return findings


def _extract_links(html: str) -> list[dict[str, str]]:
    """Return list of {href, text, href_domain} from HTML anchor tags."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        text = a.get_text(strip=True)
        try:
            domain = urlparse(href).netloc.lower()
        except Exception:
            domain = ""
        links.append({"href": href, "text": text, "href_domain": domain})
    return links


def _check_links(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    html = msg.get("html", "") or ""
    links = _extract_links(html)
    if not links:
        return findings

    shortener_count = sum(1 for lnk in links if any(lnk["href_domain"].endswith(s) for s in URL_SHORTENERS))
    if shortener_count:
        findings.append((2, f"Contains {shortener_count} shortened URL(s) (e.g. bit.ly)"))

    ip_count = sum(1 for lnk in links if IP_URL_PATTERN.match(lnk["href"]))
    if ip_count:
        findings.append((3, f"Contains {ip_count} link(s) using raw IP addresses"))

    domain_re = re.compile(r"[a-z0-9][-a-z0-9]*\.[a-z]{2,}", re.IGNORECASE)
    mismatch_count = 0
    for lnk in links:
        text_domain_match = domain_re.search(lnk["text"])
        if text_domain_match and lnk["href_domain"]:
            text_domain = text_domain_match.group(0).lower()
            if text_domain != lnk["href_domain"] and not lnk["href_domain"].endswith("." + text_domain):
                mismatch_count += 1
    if mismatch_count:
        findings.append((3, f"{mismatch_count} link(s) display a different domain than the actual URL"))

    unique_domains = {lnk["href_domain"] for lnk in links if lnk["href_domain"]}
    if len(unique_domains) > 5:
        findings.append((1, f"Links point to {len(unique_domains)} different domains"))

    return findings


def _check_structure(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    html = msg.get("html", "") or ""
    text = msg.get("text", "") or ""

    if html and not text:
        findings.append((1, "Message is HTML-only with no plain-text alternative"))

    if html:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(style=True):
            style = tag.get("style", "").lower()
            if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):
                findings.append((2, "HTML contains hidden elements (display:none / visibility:hidden)"))
                break
            if "font-size:0" in style.replace(" ", "") or "font-size: 0" in style:
                findings.append((2, "HTML contains zero-size text (font-size:0)"))
                break

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_email(msg: dict[str, Any]) -> dict[str, Any]:
    """Analyse an email message dict for scam/fraud indicators.

    Accepts the dict returned by ``fetch_inbox_message()`` with keys:
    subject, from_name, from_email, html, text, etc.

    Returns::

        {
            "risk_level": "low" | "medium" | "high",
            "score": int,
            "reasons": ["Human-readable reason", ...],
        }
    """
    all_findings: list[tuple[int, str]] = []
    all_findings.extend(_check_sender(msg))
    all_findings.extend(_check_subject(msg))
    all_findings.extend(_check_body(msg))
    all_findings.extend(_check_links(msg))
    all_findings.extend(_check_structure(msg))

    total_score = sum(score for score, _ in all_findings)
    reasons = [reason for _, reason in all_findings]

    if total_score >= HIGH_THRESHOLD:
        risk_level = "high"
    elif total_score >= MEDIUM_THRESHOLD:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_level": risk_level,
        "score": total_score,
        "reasons": reasons,
    }
