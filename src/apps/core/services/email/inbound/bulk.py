"""List, bulk and marketing mail, and Exchange Online's spam and bulk verdicts: pure functions on the headers.

**Distribution** signals say a mailing list delivered the message to its members (``List-Id``, ``List-Post``,
``Precedence: list``). The **weak** signals say only what sent it, not who wrote it: the other list headers
(``List-Unsubscribe``, which CRM and sales tools add to one-to-one mail too), an email service provider's or CRM's own
headers, ``Precedence: bulk`` or ``junk``, a no-reply sender, and Exchange's bulk complaint level (BCL, a verdict on
the sending service's reputation) at or above the threshold. A message that replies to an email the site sent is a
person's answer however it was sent, so weak signals alone do not make it bulk: they become hints on it
(``bulk_headers_on_reply``). Distribution signals still do (a reply sent to a whole list), and the spam checks
(Exchange's spam confidence level and spam verdict) apply to every message.
"""

from typing import NamedTuple

from .headers import first, joined
from .rules import (
    BCL_RE,
    BULK_PRECEDENCE,
    DISTRIBUTION_HEADERS,
    ESP_HEADERS,
    LIST_HEADERS,
    NOREPLY_RE,
    SCL_RE,
    SPAM_VERDICT_RE,
)

OVERRIDDEN = "bulk_headers_on_reply"


class Finding(NamedTuple):
    subtype: str
    signals: tuple[str, ...]


def _levels(values) -> list[int]:
    return [int(value) for value in (str(item).strip() for item in values) if value.lstrip("-").isdigit()]


def spam_confidence_level(headers) -> int | None:
    """Exchange Online's spam confidence level (SCL), the highest one the headers give; None when none does."""
    values = [first(headers, "x-ms-exchange-organization-scl")]
    values += SCL_RE.findall(joined(headers, "x-forefront-antispam-report"))
    levels = _levels(values)
    return max(levels) if levels else None


def bulk_complaint_level(headers) -> int | None:
    """Exchange Online's bulk complaint level (BCL, 0 to 9), the highest one the headers give; None when none does."""
    levels = _levels(BCL_RE.findall(joined(headers, "x-microsoft-antispam")))
    return max(levels) if levels else None


def _signals(evidence, bcl_threshold: int) -> tuple[list[str], list[str]]:
    """The distribution signals and the weak bulk signals the message carries."""
    headers = evidence.headers
    precedence = first(headers, "precedence").strip().lower()
    distribution = [name for name in DISTRIBUTION_HEADERS if name in headers]
    if precedence == "list":
        distribution.append("precedence_list")
    weak = [name for name in LIST_HEADERS if name in headers and name not in DISTRIBUTION_HEADERS]
    weak += [name for name in ESP_HEADERS if name in headers]
    if precedence in BULK_PRECEDENCE and precedence != "list":
        weak.append("precedence_bulk")
    if NOREPLY_RE.match(evidence.from_address.partition("@")[0]):
        weak.append("noreply_sender")
    bcl = bulk_complaint_level(headers)
    if bcl is not None and bcl >= bcl_threshold:
        weak.append(f"bcl_{bcl}")
    return distribution, weak


def detect(evidence, *, bcl_threshold: int) -> tuple[Finding | None, tuple[str, ...]]:
    """The list or bulk mail ``evidence`` is (or None), and the hints left on a reply to the site's mail whose weak
    bulk signals did not count."""
    distribution, weak = _signals(evidence, bcl_threshold)
    if evidence.replies_to_site_mail and not distribution:
        return None, ((OVERRIDDEN, *weak) if weak else ())
    signals = distribution + weak
    if not signals:
        return None, ()
    lists = any(name in LIST_HEADERS for name in signals) or "precedence_list" in signals
    noreply = "noreply_sender" in signals and not any(name in ESP_HEADERS for name in signals)
    return Finding("list" if lists else ("noreply" if noreply else "newsletter"), tuple(signals)), ()


def spam(headers, scl_threshold: int) -> Finding | None:
    """Spam by Exchange's verdicts: an SCL at or above the threshold, or its spam filter's verdict."""
    scl = spam_confidence_level(headers)
    if scl is not None and scl >= scl_threshold:
        return Finding("scl", (f"scl_{scl}",))
    if SPAM_VERDICT_RE.search(joined(headers, "x-forefront-antispam-report")):
        return Finding("filter_verdict", ("exchange_spam_verdict",))
    return None
