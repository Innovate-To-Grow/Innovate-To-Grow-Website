"""What the counts suggest about an address: text only, never applied.

- a spam complaint → unsubscribe them (they reported us as spam);
- a hard bounce (a Graph 5.x.x hard bounce, or an SES permanent bounce) → mark undeliverable or replace the address;
- repeated soft bounces over several days → consider marking undeliverable;
- only rejections (5.7.x) → probably our reputation or sending policy, not the address: no action;
- delays and unknown statuses → nothing.

An address already suppressed gets no suggestion. The thresholds for "repeated soft bounces" are
``EMAIL_MONITORING["address_soft_bounce_repeats"]`` and ``["address_soft_bounce_days"]``.
"""

from datetime import timedelta

from django.conf import settings

from apps.mail.models import BouncedAddress

Suggestion = BouncedAddress.Suggestion


def suggest(row: BouncedAddress) -> str:
    if row.is_suppressed:
        return ""
    if row.complaint_count:
        return Suggestion.UNSUBSCRIBE
    if row.hard_total:
        return Suggestion.UNDELIVERABLE
    config = settings.EMAIL_MONITORING
    repeats = max(1, int(config["address_soft_bounce_repeats"]))
    span = timedelta(days=max(0, int(config["address_soft_bounce_days"])))
    first, last = row.first_bounce_at, row.last_bounce_at
    if row.soft_total >= repeats and first is not None and last is not None and last - first >= span:
        return Suggestion.CONSIDER
    if row.rejected_count:
        return Suggestion.POLICY
    return ""
