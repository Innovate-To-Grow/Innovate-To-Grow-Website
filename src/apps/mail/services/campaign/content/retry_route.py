"""Determine whether the reviewed retry uses a different sending service after a sender-side refusal."""

from apps.core.models import EmailBounce, EmailServiceConfig, OutboundEmail

SENDER_REJECTIONS = {EmailBounce.Category.SPAM_REJECTED, EmailBounce.Category.RELAY_DENIED}


def rejected_sender_provider(campaign, address, source_log, *, graph_categories, lock=False) -> str | None:
    """Return None for a receiving issue, an empty string for unclear routes, or the failed provider."""
    if not SENDER_REJECTIONS.intersection(graph_categories):
        return None
    # Graph is the mailbox where a report was read. The original message may have been sent by any provider.
    telemetry = OutboundEmail.objects.filter(
        campaign_id=campaign.pk,
        recipient=address,
        source_type="mail.recipientlog",
        source_id=str(source_log.pk),
        status=OutboundEmail.Status.ACCEPTED,
    )
    if lock:
        telemetry = telemetry.select_for_update()
    providers = set(telemetry.values_list("provider", flat=True))
    providers.add(source_log.provider)
    providers.discard("")
    if len(providers) != 1:
        return ""
    provider = providers.pop()
    return provider if provider in EmailServiceConfig.Provider.values else ""


def assert_alternate_retry_route(original_provider: str | None, reviewed_provider: str) -> None:
    """Compare recorded transport identities at draft creation and again immediately before dispatch."""
    from .retry import RetryRefused

    if original_provider is None:
        return
    if not original_provider:
        raise RetryRefused("The original sending provider cannot be verified for this sender-side rejection.")
    if reviewed_provider == original_provider or reviewed_provider not in EmailServiceConfig.Provider.values:
        raise RetryRefused("This sender-side rejection requires a different configured sending provider.")
