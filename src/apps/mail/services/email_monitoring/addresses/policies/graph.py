"""Campaign holds backed by Graph DSNs bound to the original message and its failed envelope recipient."""

from django.db.models import F, OuterRef, Q, Subquery
from django.db.models.functions import Lower

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddress


def row_has_graph_hold(row) -> bool:
    cleared = row.graph_hold_cleared_at
    latest = row.trusted_graph_last_permanent_at
    return latest is not None and (cleared is None or latest > cleared)


def current_graph_permanent_reports():
    cleared = (
        BouncedAddress.objects.filter(address=OuterRef("normalized_recipient"))
        .order_by()
        .values("graph_hold_cleared_at")
    )
    return (
        EmailBounce.objects.filter(
            trusted_recipient=True,
            match_method=EmailBounce.MatchMethod.MESSAGE_ID,
            category__in=(EmailBounce.Category.HARD, EmailBounce.Category.MAILBOX_DISABLED),
        )
        .annotate(normalized_recipient=Lower("recipient"))
        .alias(hold_cleared_at=Subquery(cleared[:1]))
        .filter(Q(hold_cleared_at__isnull=True) | Q(received_at__gt=F("hold_cleared_at")))
    )


def graph_hold_addresses(addresses=None):
    """Normalized addresses with a current hold, including reports the counter has not consumed."""
    rows = BouncedAddress.objects.filter(
        Q(trusted_graph_last_permanent_at__isnull=False),
        Q(graph_hold_cleared_at__isnull=True) | Q(trusted_graph_last_permanent_at__gt=F("graph_hold_cleared_at")),
    )
    reports = current_graph_permanent_reports()
    if addresses is not None:
        rows = rows.filter(address__in=addresses)
        reports = reports.filter(normalized_recipient__in=addresses)
    return (
        rows.order_by()
        .values_list("address", flat=True)
        .union(reports.order_by().values_list("normalized_recipient", flat=True))
    )
