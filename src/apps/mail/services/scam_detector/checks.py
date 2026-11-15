from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .domains import brand_lookalike, email_domain, registrable_domain, suspicious_idn_reason
from .patterns import (
    BODY_URGENCY_PATTERNS,
    BRAND_NAMES,
    FREEMAIL_DOMAINS,
    GENERIC_GREETING_PATTERNS,
    MONEY_PATTERN,
    PERSONAL_INFO_PATTERNS,
    URGENCY_SUBJECT_PATTERNS,
)
from .structure import html_hidden_reasons


def _matched_brand(text: str, brands: list[str]) -> str:
    for brand in brands:
        match = re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def check_sender(msg: dict[str, Any], brands: list[str] = BRAND_NAMES) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    from_name = msg.get("from_name", "")
    from_email = msg.get("from_email", "")

    if not from_name:
        findings.append((1, "Sender has no display name"))

    domain = email_domain(from_email)
    if from_name and domain:
        matched = _matched_brand(from_name, brands)
        if matched and matched.lower() not in domain:
            findings.append((3, f'Display name mentions "{matched}" but email domain is {domain}'))

    if from_name and domain in FREEMAIL_DOMAINS and _matched_brand(from_name, brands):
        findings.append((2, f"Claims to be a known brand but uses freemail domain ({domain})"))

    if domain:
        idn_reason = suspicious_idn_reason(domain)
        if idn_reason:
            findings.append((3, idn_reason))
        lookalike = brand_lookalike(domain, brands)
        if lookalike:
            findings.append((3, lookalike))

    return findings


def check_authentication(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    auth = (msg.get("authentication_results", "") or "").lower()
    if not auth:
        return findings

    dmarc = re.search(r"dmarc=(\w+)", auth)
    spf = re.search(r"spf=(\w+)", auth)
    dkim = re.search(r"dkim=(\w+)", auth)

    if dmarc and dmarc.group(1) == "fail":
        findings.append((3, "Email failed DMARC authentication (sender is likely spoofed)"))
    if spf and spf.group(1) == "fail":
        findings.append((2, "Email failed SPF authentication (sending server is not authorized)"))
    elif spf and spf.group(1) == "softfail":
        findings.append((1, "Email soft-failed SPF authentication"))
    if dkim and dkim.group(1) == "fail":
        findings.append((1, "Email failed DKIM signature verification"))
    return findings


def check_address_alignment(msg: dict[str, Any]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    from_domain = registrable_domain(email_domain(msg.get("from_email", "")))
    if not from_domain:
        return findings

    reply_to = registrable_domain(email_domain(msg.get("reply_to", "")))
    return_path = registrable_domain(email_domain(msg.get("return_path", "")))

    if reply_to and reply_to != from_domain:
        findings.append((2, f"Reply-To domain ({reply_to}) differs from the sender domain ({from_domain})"))
    if return_path and return_path != from_domain:
        findings.append((1, f"Return-Path domain ({return_path}) differs from the sender domain ({from_domain})"))
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
