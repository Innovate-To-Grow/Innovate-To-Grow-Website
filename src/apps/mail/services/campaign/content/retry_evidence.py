"""Campaign-specific allowlisted evidence and fresh permanent-event blockers for retries."""

from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddressCampaign, RecipientLog

RETRYABLE_GRAPH_CATEGORIES = frozenset({"transient", "mailbox_full", "spam_rejected", "relay_denied"})


def _locked(queryset, lock: bool):
    return queryset.select_for_update() if lock else queryset


def retryable_campaign_evidence(row, campaign, address: str, *, lock: bool) -> str:
    """Return the provider source only for exact, allowlisted evidence from this campaign."""
    links = _locked(row.campaign_links.filter(campaign_id=campaign.pk, match=BouncedAddressCampaign.Match.EXACT), lock)
    for link in links:
        if link.source == BouncedAddressCampaign.Source.SES:
            if link.ses_bounced_at is not None and link.ses_bounce_type.casefold() == "transient":
                return BouncedAddressCampaign.Source.SES
            continue
        counts = link.graph_category_counts or {}
        if any(int(counts.get(category) or 0) > 0 for category in RETRYABLE_GRAPH_CATEGORIES):
            return BouncedAddressCampaign.Source.GRAPH

        # Pre-upgrade links can still be proved from a retained report that identifies the campaign. Aggregate
        # likely links never set EmailBounce.campaign_id and cannot pass this fallback.
        exact = (
            EmailBounce.objects.annotate(normalized_recipient=Lower("recipient"))
            .filter(
                campaign_id=campaign.pk,
                normalized_recipient=address,
                category__in=RETRYABLE_GRAPH_CATEGORIES,
            )
            .exclude(match_method=EmailBounce.MatchMethod.UNMATCHED)
        )
        if _locked(exact, lock).exists():
            return BouncedAddressCampaign.Source.GRAPH
    return ""


def has_unaggregated_permanent_or_complaint(address: str, *, lock: bool) -> bool:
    """Block fresh provider evidence immediately, without waiting for address aggregation."""
    ses_events = RecipientLog.objects.annotate(normalized_address=Lower("email_address")).filter(
        Q(complained_at__isnull=False) | Q(bounced_at__isnull=False, bounce_type__iexact="permanent"),
        normalized_address=address,
    )
    if _locked(ses_events, lock).exists():
        return True
    graph_events = EmailBounce.objects.annotate(normalized_recipient=Lower("recipient")).filter(
        Q(category__in=(EmailBounce.Category.HARD, EmailBounce.Category.MAILBOX_DISABLED))
        | Q(classification=EmailBounce.Classification.HARD),
        normalized_recipient=address,
    )
    return _locked(graph_events, lock).exists()
