"""Initialize trusted evidence without authorizing legacy, inferred or recipient-unbound reports."""

from email.utils import parseaddr

from django.db.models import Q


def preserve_graph_history(apps, schema_editor):
    db = schema_editor.connection.alias
    Address = apps.get_model("mail", "BouncedAddress")
    Bounce = apps.get_model("core", "EmailBounce")
    Link = apps.get_model("mail", "BouncedAddressCampaign")
    State = apps.get_model("mail", "BounceAggregationState")
    state = State.objects.using(db).select_for_update().filter(source="graph").first()
    # Earlier versions did not retain the final recipient separately from a forwarding address.
    # Keep the address history for staff, but never grant an automatic hold or retry on this alone.
    # Preserve even the coarse count for rows written by an old release without categories.
    rows = Address.objects.using(db).filter(hard_count__gt=0)
    rows.update(legacy_graph_permanent_review=True)
    links = Link.objects.using(db).filter(source="graph")
    links.exclude(graph_category_counts={}).update(graph_category_counts={})
    if state is None or state.cursor_at is None:
        return
    counted = Q(created_at__lt=state.cursor_at)
    if state.cursor_id:
        counted |= Q(created_at=state.cursor_at, pk__lte=state.cursor_id)
    by_link = {}
    reports = Bounce.objects.using(db).filter(
        counted, trusted_recipient=True, match_method="message_id", campaign_id__isnull=False
    )
    for campaign, recipient, category in reports.values_list("campaign_id", "recipient", "category").iterator():
        address = parseaddr(recipient)[1].strip().lower()
        if address and category:
            categories = by_link.setdefault((campaign, address), {})
            categories[category] = categories.get(category, 0) + 1
    for (campaign, address), categories in by_link.items():
        links.filter(campaign_id=campaign, bounced_address__address=address).update(
            match="exact", graph_category_counts=categories
        )
