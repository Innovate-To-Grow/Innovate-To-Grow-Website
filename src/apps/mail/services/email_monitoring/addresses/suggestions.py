"""What the counts suggest about an address: text only, never applied. The first that applies wins.

- a spam complaint → unsubscribe them (they reported us as spam);
- the address does not exist (a Graph report of that category, or an SES permanent bounce) → mark it undeliverable or
  replace it;
- the mailbox is disabled → replace the address, or mark it undeliverable;
- repeated temporary failures over several days (Graph reports of a temporary, full-mailbox or unknown category, SES
  transient and undetermined bounces) → consider marking it undeliverable;
- relay denied → our sending route or authorisation, not the address;
- spam or reputation rejections → our reputation, sender authentication or content, not the address;
- rejections by the recipient's policy → no action;
- delays → nothing.

Only a missing address and a disabled mailbox are evidence against the address on their own: a temporary failure
(a connection timeout, a DNS failure, an expired delivery, a full mailbox) never suggests marking an address
undeliverable unless it repeats. An address already suppressed gets no suggestion. The thresholds for "repeated" are
``EMAIL_MONITORING["address_soft_bounce_repeats"]`` and ``["address_soft_bounce_days"]``.
"""

from datetime import timedelta

from django.conf import settings

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddress

Suggestion = BouncedAddress.Suggestion
Category = EmailBounce.Category


def _repeated(row: BouncedAddress) -> bool:
    config = settings.EMAIL_MONITORING
    repeats = max(1, int(config["address_soft_bounce_repeats"]))
    span = timedelta(days=max(0, int(config["address_soft_bounce_days"])))
    first, last = row.first_bounce_at, row.last_bounce_at
    return row.temporary_total >= repeats and first is not None and last is not None and last - first >= span


def suggest(row: BouncedAddress) -> str:
    if row.is_suppressed:
        return ""
    if row.complaint_count:
        return Suggestion.UNSUBSCRIBE
    if row.category_count(Category.HARD) or row.ses_permanent_count:
        return Suggestion.UNDELIVERABLE
    if row.category_count(Category.MAILBOX_DISABLED):
        return Suggestion.REPLACE
    if _repeated(row):
        return Suggestion.CONSIDER
    for category, suggestion in (
        (Category.RELAY_DENIED, Suggestion.RELAY),
        (Category.SPAM_REJECTED, Suggestion.REPUTATION),
        (Category.POLICY_REJECTED, Suggestion.POLICY),
    ):
        if row.category_count(category):
            return suggestion
    return ""
