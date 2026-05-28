from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .patterns import (
    BODY_URGENCY_PATTERNS,
    BRAND_KEYWORDS_IN_NAME,
    FREEMAIL_DOMAINS,
    GENERIC_GREETING_PATTERNS,
    IP_URL_PATTERN,
    MONEY_PATTERN,
    PERSONAL_INFO_PATTERNS,
    URGENCY_SUBJECT_PATTERNS,
    URL_SHORTENERS,
)
from .structure import html_hidden_reasons

logger = logging.getLogger(__name__)

DOMAIN_IN_TEXT_RE = re.compile(r"(?:[a-z0-9](?:[-a-z0-9]*[a-z0-9])?\.)+[a-z]{2,}", re.IGNORECASE)


def check_sender(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    from_name = msg.get("from_name", "")
    from_email = msg.get("from_email", "")

    if not from_name:
        findings.append((1, "Sender has no display name"))

    email_domain = from_email.rsplit("@", 1)[-1].lower() if "@" in from_email else ""
    if from_name and email_domain:
        brand_match = BRAND_KEYWORDS_IN_NAME.search(from_name)
        if brand_match and brand_match.group(1).lower() not in email_domain:
            findings.append(
                (
                    3,
                    (f'Display name mentions "{brand_match.group(1)}" but email domain is {email_domain}'),
                )
            )

    if from_name and email_domain in FREEMAIL_DOMAINS:
        if BRAND_KEYWORDS_IN_NAME.search(from_name):
            findings.append((2, f"Claims to be a known brand but uses freemail domain ({email_domain})"))

    return findings


def check_subject(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    subject = msg.get("subject", "")
    hits = [pattern.pattern for pattern in URGENCY_SUBJECT_PATTERNS if pattern.search(subject)]
    if hits:
        findings.append(
            (
                min(len(hits) + 1, 4),
                f"Subject contains urgency/scam language ({len(hits)} pattern(s) matched)",
            )
        )
    if subject.isupper() and len(subject) > 10:
        findings.append((1, "Subject is written entirely in UPPERCASE"))
    return findings


def check_body(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    body = body_text(msg)
    if not body:
        return findings

    urgency_hits = sum(1 for pattern in BODY_URGENCY_PATTERNS if pattern.search(body))
    if urgency_hits >= 2:
        findings.append(
            (
                min(urgency_hits, 4),
                f"Body contains urgency/pressure language ({urgency_hits} pattern(s))",
            )
        )
    elif urgency_hits == 1:
        findings.append((1, "Body contains urgency/pressure language"))

    info_hits = [pattern.pattern for pattern in PERSONAL_INFO_PATTERNS if pattern.search(body)]
    if info_hits:
        findings.append(
            (
                min(len(info_hits) + 2, 5),
                f"Body requests personal/financial information ({len(info_hits)} type(s))",
            )
        )

    if any(pattern.search(body) for pattern in GENERIC_GREETING_PATTERNS):
        findings.append((1, 'Uses generic greeting (e.g. "Dear Customer")'))

    money_matches = MONEY_PATTERN.findall(body)
    if len(money_matches) >= 2:
        findings.append((2, f"Body mentions large monetary amounts ({len(money_matches)} occurrence(s))"))
    elif money_matches:
        findings.append((1, "Body mentions a monetary amount"))

    return findings


def check_links(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    links = extract_links(msg.get("html", "") or "")
    if not links:
        return findings

    shortener_count = sum(
        1 for link in links if any(link["href_domain"].endswith(shortener) for shortener in URL_SHORTENERS)
    )
    if shortener_count:
        findings.append((2, f"Contains {shortener_count} shortened URL(s) (e.g. bit.ly)"))

    ip_count = sum(1 for link in links if IP_URL_PATTERN.match(link["href"]))
    if ip_count:
        findings.append((3, f"Contains {ip_count} link(s) using raw IP addresses"))

    mismatch_details = mismatched_link_details(links)
    if mismatch_details:
        findings.append(
            (
                3,
                f"{len(mismatch_details)} link(s) display a different domain than the actual URL",
            )
        )

    unique_domains = {link["href_domain"] for link in links if link["href_domain"]}
    if len(unique_domains) > 5:
        findings.append((1, f"Links point to {len(unique_domains)} different domains"))

    return findings


def check_structure(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    html = msg.get("html", "") or ""
    text = msg.get("text", "") or ""

    if html and not text:
        findings.append((1, "Message is HTML-only with no plain-text alternative"))
    if html:
        findings.extend((2, reason) for reason in html_hidden_reasons(html))
    return findings


def body_text(msg: dict[str, Any]) -> str:
    text = msg.get("text", "") or ""
    if text.strip():
        return text
    html = msg.get("html", "") or ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True) if html else ""


def extract_links(html: str) -> list[dict[str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        try:
            domain = normalize_domain(urlparse(href).hostname or "")
        except Exception:
            logger.debug("Failed to parse link domain from %r", href, exc_info=True)
            domain = ""
        links.append({"href": href, "text": anchor.get_text(strip=True), "href_domain": domain})
    return links


def mismatched_link_count(links: list[dict[str, str]]) -> int:
    return len(mismatched_link_details(links))


def mismatched_link_details(links: list[dict[str, str]]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for link in links:
        text_domain = displayed_domain(link["text"])
        href_domain = link["href_domain"]
        if not text_domain or not href_domain:
            continue
        if not domains_match(text_domain, href_domain):
            details.append(
                {
                    "type": "domain_mismatch",
                    "label": "Displayed domain does not match destination",
                    "display_domain": text_domain,
                    "actual_domain": href_domain,
                }
            )
    return details


def link_warning_details(msg: dict[str, Any]) -> list[dict[str, str]]:
    return mismatched_link_details(extract_links(msg.get("html", "") or ""))


_FILE_EXTENSIONS = frozenset(
    {
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "zip",
        "rar",
        "tar",
        "gz",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "webp",
        "mp4",
        "mp3",
        "wav",
        "csv",
        "txt",
        "json",
        "xml",
        "html",
        "css",
        "exe",
        "dmg",
        "apk",
        "iso",
    }
)


def displayed_domain(link_text: str) -> str:
    match = DOMAIN_IN_TEXT_RE.search(link_text)
    if not match:
        return ""
    candidate = normalize_domain(match.group(0))
    parts = candidate.rsplit(".", 1)
    if len(parts) == 2 and parts[1] in _FILE_EXTENSIONS:
        return ""
    return candidate


def normalize_domain(domain: str) -> str:
    domain = domain.lower().strip().rstrip(".")
    return domain[4:] if domain.startswith("www.") else domain


def domains_match(display_domain: str, href_domain: str) -> bool:
    display_domain = normalize_domain(display_domain)
    href_domain = normalize_domain(href_domain)
    if href_domain == display_domain:
        return True
    return href_domain.endswith("." + display_domain) or display_domain.endswith("." + href_domain)
