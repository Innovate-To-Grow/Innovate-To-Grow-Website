"""Mail → Delivery Operations → Email Monitoring: the overview, the email log, one email's history, the bounce list,
one campaign's monitoring, and the bounce processor's controls (scan now, pause, resume, and in ``controls``
"Rescan since" and the first-scan lookback). The Bounced addresses tab is in ``addresses`` and ``address_actions``,
the Amazon SES tab (the former Delivery Dashboard) in ``ses``.

``admin_view`` only requires a staff login, so every view also requires the Mail app (``user_can_access_app``).
Every page is read-only except the bounce-processing POST.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import EmailBounce, EmailCategory, OutboundEmail
from apps.core.services.email.bounces import active_reader, run_now
from apps.core.services.email.bounces.state import is_paused, set_paused
from apps.core.services.email.telemetry import KIND_LABELS
from apps.core.utils.access import user_can_access_app
from apps.mail.models import EmailCampaign
from apps.mail.services.email_monitoring import campaigns, charts, detail, health, log, overview, scope

from . import controls

TEMPLATES = "admin/mail/email_monitoring"


def require_mail_access(request) -> None:
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied


def _context(request, title: str, current: scope.Scope | None, section: str) -> dict:
    query = urlencode(current.params()) if current is not None else ""
    return {
        **admin.site.each_context(request),
        "title": title,
        "page_title": title,
        "section": section,
        "scope": current,
        "scope_query": query,
        "presets": [{"key": key, "label": label} for key, (label, _span) in scope.PRESETS.items()],
        "providers": scope.PROVIDERS,
        "health": health.monitoring_health(),
    }


def overview_view(request):
    require_mail_access(request)
    current = scope.parse_scope(request.GET)
    context = _context(request, "Email Monitoring", current, "overview")
    context.update(
        figures=overview.overview(current),
        chart_data=charts.charts(current),
        failure_reasons=charts.failure_reasons(current),
        bounce_reasons=charts.bounce_reasons(current),
        comparisons=campaigns.comparisons(current),
        probe_count=OutboundEmail.objects.filter(
            category=EmailCategory.ACCESS_CHECK, created_at__gte=current.start, created_at__lt=current.end
        ).count(),
        send_rate=overview.send_rate(),
    )
    return TemplateResponse(request, f"{TEMPLATES}/overview.html", context)


def overview_data_view(request):
    require_mail_access(request)
    current = scope.parse_scope(request.GET)
    return JsonResponse(
        {
            "range": {"key": current.key, "start": current.start, "end": current.end, "label": current.label},
            "provider": current.provider,
            "figures": overview.overview(current),
            "charts": charts.charts(current),
        }
    )


def _listing_queries(current: scope.Scope, listing: log.Listing) -> dict:
    """``filter_query`` (scope and filters: sort links add the sort) and ``page_query`` (all of it: page links)."""
    filters = {**current.params(), **{key: value for key, value in listing.filters.items() if value}}
    order = {"page_size": listing.page_size, "sort": listing.sort, "dir": "desc" if listing.descending else "asc"}
    return {"filter_query": urlencode(filters), "page_query": urlencode({**filters, **order})}


def email_log_view(request):
    require_mail_access(request)
    current = scope.parse_scope(request.GET)
    listing = log.email_listing(request.GET)
    page = log.paginate(log.email_rows(current, listing), listing)
    page.object_list = list(page.object_list)
    names = dict(
        EmailCampaign.objects.filter(
            pk__in={row.campaign_id for row in page.object_list if row.campaign_id}
        ).values_list("pk", "name")
    )
    for row in page.object_list:
        row.campaign_name = names.get(row.campaign_id) or ("(deleted campaign)" if row.campaign_id else "")
    context = _context(request, "Email Log", current, "emails")
    context.update(
        page=page,
        listing=listing,
        **_listing_queries(current, listing),
        categories=EmailCategory.choices,
        statuses=OutboundEmail.Status.choices,
        deliveries=OutboundEmail.DeliveryStatus.choices,
        error_kinds=sorted(KIND_LABELS.items(), key=lambda item: item[1]),
        page_sizes=log.PAGE_SIZES,
        sorts=log.EMAIL_SORTS,
    )
    return TemplateResponse(request, f"{TEMPLATES}/emails.html", context)


def email_detail_view(request, pk):
    require_mail_access(request)
    email = get_object_or_404(OutboundEmail, pk=pk)
    context = _context(request, "Outgoing Email", None, "emails")
    context.update(detail.email_detail(email))
    return TemplateResponse(request, f"{TEMPLATES}/email_detail.html", context)


def bounce_list_view(request):
    require_mail_access(request)
    current = scope.parse_scope(request.GET)
    listing = log.bounce_listing(request.GET)
    page = log.paginate(log.bounce_rows(current, listing), listing)
    context = _context(request, "Bounce Reports", current, "bounces")
    context.update(
        page=page,
        listing=listing,
        **_listing_queries(current, listing),
        classifications=EmailBounce.Classification.choices,
        categories=EmailBounce.Category.choices,
        category_legend=EmailBounce.category_legend(),
        match_methods=EmailBounce.MatchMethod.choices,
        page_sizes=log.PAGE_SIZES,
        sorts=log.BOUNCE_SORTS,
    )
    return TemplateResponse(request, f"{TEMPLATES}/bounces.html", context)


def campaign_view(request, pk):
    require_mail_access(request)
    campaign = get_object_or_404(EmailCampaign, pk=pk)
    context = _context(request, f"Campaign Monitoring - {campaign.name or campaign.subject}", None, "campaign")
    # The campaign's emails in the log: from the day it was sent (at most a year of it) to today.
    today = timezone.localdate()
    first_day = max(timezone.localdate(campaign.sent_at or campaign.created_at), today - timedelta(days=365))
    monitoring = campaigns.campaign_monitoring(campaign)
    context.update(
        campaign=campaign,
        monitoring=monitoring,
        chart_payload={"campaign": monitoring["timeline"]},
        campaign_link=reverse("admin:mail_emailcampaign_change", args=[campaign.pk]),
        log_query=urlencode(
            {"range": "custom", "start": first_day.isoformat(), "end": today.isoformat(), "campaign": campaign.pk}
        ),
    )
    return TemplateResponse(request, f"{TEMPLATES}/campaign.html", context)


@require_POST
def bounce_processing_view(request):
    """Scan now, pause, resume, rescan since a time, or set the first-scan lookback of the Graph sending mailbox.

    A scan and a rescan need a mailbox the processor can read (the time a rescan sets is read by the next scan); the
    lookback, like pause and resume, needs only the mailbox."""
    require_mail_access(request)
    action = request.POST.get("action")
    reader, mailbox, problem = active_reader()
    target = reverse("admin:mail_email_monitoring")
    if action == "scan" and reader is not None:
        _scan_now(request, mailbox)
    elif action in ("pause", "resume") and mailbox:
        set_paused(mailbox, action == "pause")
        verb = "paused" if action == "pause" else "resumed"
        messages.success(request, f"Bounce processing for {mailbox} {verb}.")
    elif action == "rescan" and reader is not None:
        controls.rescan(request, mailbox)
    elif action == "lookback" and mailbox:
        controls.lookback(request, mailbox)
    else:
        messages.error(request, problem or "Unknown bounce processing action.")
    return HttpResponseRedirect(target)


def _scan_now(request, mailbox: str) -> None:
    """Queue a scan at once, unless processing is paused (the scan would read nothing: resume first) or switched off.
    The card offers no working button then; this answers a stale page or a second tab the same way."""
    if is_paused(mailbox):
        messages.warning(request, f"Bounce processing for {mailbox} is paused: resume it to scan.")
    elif run_now():
        messages.success(request, "A bounce scan was queued; the background worker runs it within a minute.")
    else:
        messages.warning(request, "Bounce processing is turned off (EMAIL_BOUNCE_PROCESSING_ENABLED).")
