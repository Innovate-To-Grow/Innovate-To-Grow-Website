"""Email Monitoring → Bounced addresses: one address's detail page (member card, notices, campaigns, actions)."""

from urllib.parse import urlencode

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.models import EmailBounce
from apps.core.utils.access import user_can_access_app
from apps.event.models import EventRegistration
from apps.mail.admin.email_monitoring.addresses import REPORTS_SHOWN, _member_link
from apps.mail.models import BouncedAddress, EmailCampaign, RecipientLog
from apps.mail.services.audience.suppression import is_suppressed, normalize_address
from apps.mail.services.campaign.content.retry import retry_address_for
from apps.mail.services.email_monitoring.addresses.actions.guards import availability
from apps.mail.services.email_monitoring.addresses.actions.specs import SPECS
from apps.mail.services.email_monitoring.addresses.actions.targets import load_target
from apps.mail.services.email_monitoring.addresses.listing.matching import (
    refresh_cached_links,
)

from .views import TEMPLATES, _context, require_mail_access


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


def _notice_link(request, row) -> str:
    """The helpdesk ticket holding the latest left-the-organisation notice, for staff with the Helpdesk app (the
    queue hides automated mail by default, so the link shows every ticket)."""
    if not row.left_org_hint_is_current or not row.left_org_ticket or not user_can_access_app(request.user, "helpdesk"):
        return ""
    query = urlencode({"q": row.left_org_ticket, "mail": "all", "status": "any"})
    return f"{reverse('admin:helpdesk_ticket_changelist')}?{query}"


def _detail_campaigns(row) -> list:
    links = list(row.campaign_links.order_by("-last_at"))
    campaigns = EmailCampaign.objects.in_bulk({link.campaign_id for link in links})
    result = []
    for link in links:
        campaign = campaigns.get(link.campaign_id)
        retry_url = ""
        if campaign and retry_address_for(campaign, row.address):
            retry_url = reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[campaign.pk])
            retry_url += "?" + urlencode({"retry_address": row.address})
        result.append(
            {
                "link": link,
                "name": campaign.name if campaign else None,
                "exists": campaign is not None,
                "retry_url": retry_url,
            }
        )
    return result


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
        campaign_held=is_suppressed(row.address),
        target=target,
        actions=actions,
        cards=[_member_card(request, owner) for owner in target.owners],
        reports=list(reports[:REPORTS_SHOWN]),
        report_count=reports.count(),
        ses_events=list(ses_events[:REPORTS_SHOWN]),
        campaign_links=_detail_campaigns(row),
        history=list(row.actions.select_related("actor").order_by("-created_at")[:REPORTS_SHOWN]),
        contact_admin=user_can_access_app(request.user, "authn"),
        notice_link=_notice_link(request, row),
        shown=REPORTS_SHOWN,
        category_legend=EmailBounce.category_legend(),
    )
    return TemplateResponse(request, f"{TEMPLATES}/addresses/address_detail.html", context)
