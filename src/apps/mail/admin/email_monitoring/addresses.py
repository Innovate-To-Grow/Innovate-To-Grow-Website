"""Email Monitoring → Bounced addresses: the list (filters, status tabs, bulk selection, export) and one address's
page (its reports, its member, its actions and their history).

Every view requires the Mail app (``admin_view`` only checks ``is_staff``). Loading the list first counts a bounded
batch of new reports (``aggregate.run``); it never changes a member, a contact email or a subscription. Members are
linked for staff who also hold the Members (``authn``) app.
"""

import logging
from collections import defaultdict
from urllib.parse import urlencode

from django.conf import settings
from django.db import DatabaseError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from apps.core.models import EmailBounce
from apps.core.utils.access import user_can_access_app
from apps.event.models import EventRegistration
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, EmailCampaign, RecipientLog
from apps.mail.services.email_monitoring.addresses import aggregate, listing
from apps.mail.services.email_monitoring.addresses.export import export_rows
from apps.mail.services.email_monitoring.addresses.guards import Target, availability, load_target
from apps.mail.services.email_monitoring.addresses.matching import (
    AddressMatch,
    match_addresses,
    refresh_cached_links,
)
from apps.mail.services.email_monitoring.addresses.specs import QUICK_ACTIONS, SPECS
from apps.mail.services.suppression import normalize_address

from .views import TEMPLATES, _context, require_mail_access

# A display cap for one address's page (older rows stay counted; the export and the bounce list have them all).
REPORTS_SHOWN = 200
logger = logging.getLogger(__name__)


def _member_link(request, member) -> str:
    if member is None or not user_can_access_app(request.user, "authn"):
        return ""
    return reverse("admin:authn_member_change", args=[member.pk])


def _campaigns_by_row(rows) -> dict:
    """``{row id: {"count": n, "last": {...} or None}}`` from the rows' campaign links (two queries)."""
    links = list(
        BouncedAddressCampaign.objects.filter(bounced_address__in=rows)
        .order_by("last_at")
        .values("bounced_address_id", "campaign_id", "match", "last_at")
    )
    names = dict(EmailCampaign.objects.filter(pk__in={link["campaign_id"] for link in links}).values_list("pk", "name"))
    grouped = defaultdict(dict)
    for link in links:
        grouped[link["bounced_address_id"]][link["campaign_id"]] = link
    found = {}
    for row_id, campaigns in grouped.items():
        last = max(campaigns.values(), key=lambda link: (link["last_at"] is not None, link["last_at"] or 0))
        found[row_id] = {
            "count": len(campaigns),
            "last": {
                "id": last["campaign_id"],
                "name": names.get(last["campaign_id"]) or "(deleted campaign)",
                "exists": last["campaign_id"] in names,
                "likely": last["match"] == BouncedAddressCampaign.Match.LIKELY,
            },
        }
    return found


def _entry(request, row, match: AddressMatch, campaigns: dict) -> dict:
    target = Target(row=row, match=match)
    member = match.member
    quick = []
    for action in QUICK_ACTIONS:
        verdict = availability(action, request, target)
        if verdict.allowed:
            quick.append({"action": action, "label": SPECS[action].label})
    return {
        "row": row,
        "match": match,
        "member": member,
        "member_link": _member_link(request, member),
        "owners": [{"member": owner, "link": _member_link(request, owner)} for owner in match.owners],
        "contact": match.contact,
        "campaigns": campaigns.get(row.pk, {"count": 0, "last": None}),
        "quick": quick,
    }


def _count_new_reports() -> dict:
    """Count a bounded batch of new reports before showing the list. Best effort: the hourly maintenance counts
    whatever a page load leaves (or fails on), so a database error here never breaks the page."""
    try:
        return aggregate.run(max_rows=int(settings.EMAIL_MONITORING["address_page_rows"]), wait=False)
    except DatabaseError:
        logger.warning("Counting new bounce reports for the Bounced addresses page failed", exc_info=True)
        return {"graph": 0, "ses": 0, "busy": False, "failed": True}


def address_list_view(request):
    require_mail_access(request)
    counted = _count_new_reports()
    current = listing.parse_listing(request.GET)
    page = listing.paginate(listing.rows_for(current), current)
    rows = list(page.object_list)
    matches = match_addresses(row.address for row in rows)
    refresh_cached_links(rows, matches)
    campaigns = _campaigns_by_row(rows)
    filters = current.query()
    order = {"page_size": current.page_size, "sort": current.sort, "dir": "desc" if current.descending else "asc"}
    context = _context(request, "Bounced Addresses", None, "addresses")
    context.update(
        page=page,
        entries=[_entry(request, row, matches[row.address], campaigns) for row in rows],
        listing=current,
        filter_query=urlencode(filters),
        page_query=urlencode({**filters, **order}),
        status_query=urlencode({key: value for key, value in filters.items() if key != "status"}),
        status_counts=listing.status_counts(current.filters),
        statuses=BouncedAddress.Status.choices,
        types=[(key, label) for key, (label, _q) in listing.TYPES.items()],
        categories=[(key, label) for key, (label, _q) in listing.CATEGORIES.items()],
        category_legend=EmailBounce.category_legend(),
        roles=BouncedAddress.Role.choices,
        member_states=[(key, label) for key, (label, _q) in listing.MEMBER_STATES.items()],
        suggestions=BouncedAddress.Suggestion.choices,
        campaigns=listing.campaign_options(),
        page_sizes=listing.PAGE_SIZES,
        sorts=listing.SORTS,
        bulk_actions=[(action, SPECS[action].label) for action in QUICK_ACTIONS],
        pending=aggregate.pending(),
        counted=counted,
        suppressed_total=BouncedAddress.objects.filter(suppressed_at__isnull=False).count(),
        evidence_choices=[(key, label) for key, (label, _q) in listing.EVIDENCE.items()],
        can_rebuild=bool(request.user.is_superuser),
    )
    return TemplateResponse(request, f"{TEMPLATES}/addresses.html", context)


def addresses_export_view(request):
    require_mail_access(request)
    current = listing.parse_listing(request.GET)
    content = export_rows(listing.rows_for(current))
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
    response["Content-Disposition"] = f'attachment; filename="bounced_addresses_{stamp}.xlsx"'
    return response


def _member_card(request, member) -> dict:
    """The member's card. Their other addresses (and which are verified) and their phones are shown only to staff
    with the Members (``authn``) app, as the Member admin would: they are sign-in factors."""
    card = {
        "member": member,
        "link": _member_link(request, member),
        "registrations": EventRegistration.objects.filter(member=member).count(),
        "contacts": None,
    }
    if not user_can_access_app(request.user, "authn"):
        return card
    contacts = list(member.contact_emails.order_by("created_at", "pk"))
    suppressed = set(
        BouncedAddress.objects.filter(
            address__in=[normalize_address(contact.email_address) for contact in contacts], suppressed_at__isnull=False
        ).values_list("address", flat=True)
    )
    card.update(
        contacts=[
            {"contact": contact, "suppressed": normalize_address(contact.email_address) in suppressed}
            for contact in contacts
        ],
        verified_phones=member.contact_phones.filter(verified=True).count(),
        phones=member.contact_phones.count(),
    )
    return card


def _detail_campaigns(row) -> list:
    links = list(row.campaign_links.order_by("-last_at"))
    names = dict(EmailCampaign.objects.filter(pk__in={link.campaign_id for link in links}).values_list("pk", "name"))
    return [{"link": link, "name": names.get(link.campaign_id), "exists": link.campaign_id in names} for link in links]


def address_detail_view(request, pk):
    require_mail_access(request)
    row = get_object_or_404(BouncedAddress.objects.select_related("reviewed_by", "suppressed_by"), pk=pk)
    target = load_target(row)
    refresh_cached_links([row], {row.address: target.match})
    actions = []
    for action, spec in SPECS.items():
        verdict = availability(action, request, target)
        actions.append({"action": action, "spec": spec, "allowed": verdict.allowed, "reason": verdict.reason})
    reports = EmailBounce.objects.filter(recipient__iexact=row.address).order_by("-received_at")
    ses_events = (
        RecipientLog.objects.filter(email_address__iexact=row.address)
        .filter(Q(bounced_at__isnull=False) | Q(complained_at__isnull=False))
        .select_related("campaign")
        .order_by("-updated_at")
    )
    context = _context(request, f"Bounced Address - {row.address}", None, "addresses")
    context.update(
        row=row,
        target=target,
        actions=actions,
        cards=[_member_card(request, owner) for owner in target.owners],
        reports=list(reports[:REPORTS_SHOWN]),
        report_count=reports.count(),
        ses_events=list(ses_events[:REPORTS_SHOWN]),
        campaign_links=_detail_campaigns(row),
        history=list(row.actions.select_related("actor").order_by("-created_at")[:REPORTS_SHOWN]),
        contact_admin=user_can_access_app(request.user, "authn"),
        shown=REPORTS_SHOWN,
        category_legend=EmailBounce.category_legend(),
    )
    return TemplateResponse(request, f"{TEMPLATES}/address_detail.html", context)
