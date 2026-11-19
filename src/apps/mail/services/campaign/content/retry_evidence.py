"""Campaign-specific allowlisted evidence and fresh permanent-event blockers for retries."""

from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddressCampaign, RecipientLog
from apps.mail.services.email_monitoring.addresses.policies.graph import current_graph_permanent_reports
from apps.mail.services.email_monitoring.addresses.policies.ses import retryable_ses_link, ses_handling

RETRYABLE_GRAPH_CATEGORIES = frozenset({"transient", "mailbox_full", "spam_rejected", "relay_denied"})


def _locked(queryset, lock: bool):
    return queryset.select_for_update() if lock else queryset


def graph_campaign_categories(row, campaign, address: str, *, lock: bool = False) -> set[str]:
    """Trust only per-event evidence that matched the original Message-ID *and* the bounced envelope address."""
    links = row.campaign_links.filter(
        campaign_id=campaign.pk, source=BouncedAddressCampaign.Source.GRAPH, match=BouncedAddressCampaign.Match.EXACT
    )
    categories = set()
    for counts in _locked(links, lock).values_list("graph_category_counts", flat=True):
        categories.update(category for category, count in (counts or {}).items() if count > 0)
    reports = EmailBounce.objects.filter(
        campaign_id=campaign.pk,
        trusted_recipient=True,
        match_method=EmailBounce.MatchMethod.MESSAGE_ID,
        recipient__iexact=address,
    )
    categories.update(_locked(reports, lock).values_list("category", flat=True))
    return categories


def retryable_campaign_evidence(row, campaign, address: str, *, lock: bool, source_log, graph_categories=None) -> str:
    """Return the source only for exact, allowlisted evidence from this campaign."""
    links = row.campaign_links.filter(
        campaign_id=campaign.pk, source=BouncedAddressCampaign.Source.SES, match=BouncedAddressCampaign.Match.EXACT
    )
    if (
        source_log.bounced_at
        and ses_handling(source_log.bounce_type, source_log.bounce_subtype, source_log.diagnostic_code) != "temporary"
    ):
        return ""
    has_ses_evidence = False
    for link in _locked(links, lock):
        if link.ses_complained_at:
            return ""
        if link.ses_bounced_at:
            if not retryable_ses_link(link):
                return ""
            has_ses_evidence = True
    if has_ses_evidence:
        return BouncedAddressCampaign.Source.SES
    if graph_categories is None:
        graph_categories = graph_campaign_categories(row, campaign, address, lock=lock)
    if RETRYABLE_GRAPH_CATEGORIES.intersection(graph_categories):
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
    graph_events = current_graph_permanent_reports().filter(normalized_recipient=address)
    return _locked(graph_events, lock).exists()
