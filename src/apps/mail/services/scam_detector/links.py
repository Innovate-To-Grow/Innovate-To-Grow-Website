"""The link check and the link reading it uses: hrefs, bare URLs, their domains and mismatched link text."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .checks import body_text
from .domains import brand_lookalike, suspicious_idn_reason
from .patterns import (
    BRAND_NAMES,
    IP_URL_PATTERN,
    URL_SHORTENERS,
)

logger = logging.getLogger(__name__)

DOMAIN_IN_TEXT_RE = re.compile(r"(?:[a-z0-9](?:[-a-z0-9]*[a-z0-9])?\.)+[a-z]{2,}", re.IGNORECASE)
TEXT_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def check_links(msg: dict[str, Any], brands: list[str] = BRAND_NAMES) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    anchors = extract_links(msg.get("html", "") or "")
    # Also scan plain-body URLs (raw text isn't wrapped in <a> tags).
    links = _dedupe_links(anchors + extract_text_urls(body_text(msg)))
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

    # Displayed-vs-actual mismatch only applies to anchors (raw URLs have no link text).
    mismatch_details = mismatched_link_details(anchors)
    if mismatch_details:
        findings.append(
            (
                3,
                f"{len(mismatch_details)} link(s) display a different domain than the actual URL",
            )
        )

    idn_reasons = {reason for link in links if (reason := suspicious_idn_reason(link["href_domain"]))}
    if idn_reasons:
        findings.append((3, f"{len(idn_reasons)} link domain(s) use punycode or non-ASCII look-alike characters"))

    brand_reasons = {reason for link in links if (reason := brand_lookalike(link["href_domain"], brands))}
    if brand_reasons:
        if len(brand_reasons) == 1:
            findings.append((3, next(iter(brand_reasons))))
        else:
            findings.append((3, f"{len(brand_reasons)} link domain(s) impersonate known brands"))

    unique_domains = {link["href_domain"] for link in links if link["href_domain"]}
    if len(unique_domains) > 5:
        findings.append((1, f"Links point to {len(unique_domains)} different domains"))

    return findings


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


def extract_text_urls(text: str) -> list[dict[str, str]]:
    if not text:
        return []
    links: list[dict[str, str]] = []
    for raw in TEXT_URL_RE.findall(text):
        href = raw.rstrip(".,;:!?)\"'")
        try:
            domain = normalize_domain(urlparse(href).hostname or "")
        except Exception:
            logger.debug("Failed to parse text URL %r", href, exc_info=True)
            domain = ""
        links.append({"href": href, "text": "", "href_domain": domain})
    return links


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for link in links:
        if link["href"] in seen:
            continue
        seen.add(link["href"])
        deduped.append(link)
    return deduped


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
