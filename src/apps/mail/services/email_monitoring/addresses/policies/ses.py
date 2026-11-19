"""Interpret a signed SES notification for staff review and eligibility to retry."""

from collections import Counter

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.classify import classify
from apps.core.services.email.inbound.classification.rules import VACATION_RE

Category = EmailBounce.Category
RECEIVING = {Category.MAILBOX_FULL, Category.TRANSIENT}
INVALID = {Category.HARD, Category.MAILBOX_DISABLED}
CONTENT_SUBTYPES = {"attachmentrejected", "contentrejected", "messagetoolarge"}


def ses_handling(bounce_type: str, subtype: str, diagnostic: str) -> str:
    kind = bounce_type.casefold()
    subtype = subtype.casefold()
    if kind == "permanent":
        if subtype not in {"", "general"}:
            return "provider_hold"
        verdict = classify("failed", "", diagnostic)
        return "invalid" if verdict and verdict.category in INVALID else "provider_hold"
    if kind != "transient":
        return "review"
    if subtype in CONTENT_SUBTYPES:
        return "content"
    if subtype == "mailboxfull":
        return "temporary"
    if subtype not in {"", "general"}:
        return "review"
    if VACATION_RE.search(diagnostic[:1000]):
        return "vacation"
    verdict = classify("failed", "", diagnostic)
    return "temporary" if verdict and verdict.category in RECEIVING else "review"


def retryable_ses_link(link) -> bool:
    return bool(
        link.ses_bounced_at
        and not link.ses_complained_at
        and ses_handling(link.ses_bounce_type, link.ses_bounce_subtype, link.ses_diagnostic) == "temporary"
    )


def review_counts(links) -> dict:
    return dict(
        Counter(
            ses_handling(link.ses_bounce_type, link.ses_bounce_subtype, link.ses_diagnostic)
            for link in links
            if link.ses_bounced_at
        )
    )
