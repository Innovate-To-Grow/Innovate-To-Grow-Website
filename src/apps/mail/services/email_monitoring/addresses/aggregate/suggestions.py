"""Address-level guidance prioritizes complaints and holds, staff-reviewed contacts, message and sending faults,
then repeated receiving failures. Unexplained Graph or SES failures need evidence review. A suggestion never grants
campaign retry eligibility. The repeated-failure count and minimum report span come from EMAIL_MONITORING.
"""

from datetime import timedelta

from django.conf import settings

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddress
from apps.mail.services.email_monitoring.addresses.policies.graph import row_has_graph_hold

Suggestion = BouncedAddress.Suggestion
Category = EmailBounce.Category


def _repeated(row: BouncedAddress) -> bool:
    config = settings.EMAIL_MONITORING
    repeats = max(1, int(config["address_soft_bounce_repeats"]))
    span = timedelta(days=max(0, int(config["address_soft_bounce_days"])))
    first, last = row.first_bounce_at, row.last_bounce_at
    return row.temporary_total >= repeats and first is not None and last is not None and last - first >= span


def _permanent_suggestion(row, ses):
    if ses.get("provider_hold"):
        return Suggestion.SES_HOLD
    if ses.get("invalid"):
        return Suggestion.UNDELIVERABLE
    if row_has_graph_hold(row):
        if row.trusted_graph_hard_count:
            return Suggestion.UNDELIVERABLE
        if row.trusted_graph_disabled_count:
            return Suggestion.REPLACE
        return Suggestion.VERIFY_EVIDENCE
    if row.legacy_graph_permanent_review:
        return Suggestion.VERIFY_EVIDENCE
    return ""


def suggest(row: BouncedAddress) -> str:
    if row.is_suppressed:
        return ""
    if row.complaint_count:
        return Suggestion.UNSUBSCRIBE
    ses = (row.ses_last or {}).get("review_counts") or {}
    permanent = _permanent_suggestion(row, ses)
    if permanent:
        return permanent
    if row.left_org_count:
        return Suggestion.LEFT_ORG
    if ses.get("content"):
        return Suggestion.FIX_CONTENT
    if row.ses_permanent_count and not ses:
        return Suggestion.SES_HOLD
    for category, suggestion in (
        (Category.RELAY_DENIED, Suggestion.RELAY),
        (Category.SPAM_REJECTED, Suggestion.REPUTATION),
    ):
        if row.category_count(category):
            return suggestion
    if ses.get("review") or (not ses and (row.ses_transient_count or row.ses_undetermined_count)):
        return Suggestion.VERIFY_EVIDENCE
    if _repeated(row):
        return Suggestion.CONSIDER
    if row.category_count(Category.POLICY_REJECTED):
        return Suggestion.POLICY
    if row.category_count(Category.UNKNOWN):
        return Suggestion.VERIFY_EVIDENCE
    if not row.graph_hold_cleared_at and (
        row.category_count(Category.HARD) or row.category_count(Category.MAILBOX_DISABLED)
    ):
        return Suggestion.VERIFY_EVIDENCE
    return ""
