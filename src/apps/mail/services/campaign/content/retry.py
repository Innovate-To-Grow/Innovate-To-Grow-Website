"""Safety policy for a one-address retry of a campaign bounce.

A retry is not a generic Manual Emails campaign.  It is tied to exact, retryable evidence from one source campaign,
one live verified/subscribed contact, and the sending method staff reviewed when the draft was created.  The policy
is intentionally checked at offer, creation, queueing and immediately before a provider call.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models.functions import Lower

from apps.authn.models import ContactEmail, Member
from apps.mail.models import BouncedAddress, EmailCampaign, RecipientLog
from apps.mail.services.audience.suppression import normalize_address
from apps.mail.services.email_monitoring.addresses.policies.graph import row_has_graph_hold

from .retry_evidence import (
    graph_campaign_categories,
    has_unaggregated_permanent_or_complaint,
    retryable_campaign_evidence,
)
from .retry_route import assert_alternate_retry_route, rejected_sender_provider


class RetryRefused(ValueError):
    """The requested retry no longer satisfies its safety policy."""


@dataclass(frozen=True)
class RetryEligibility:
    address: str
    contact_email_id: object
    member_id: object
    evidence_source: str
    rejected_sender_provider: str | None


def _locked(queryset, lock: bool):
    return queryset.select_for_update() if lock else queryset


def _unique_live_contact(address: str, *, lock: bool):
    contacts = list(
        _locked(
            ContactEmail.objects.annotate(normalized_address=Lower("email_address")).filter(normalized_address=address),
            lock,
        )[:2]
    )
    if len(contacts) != 1:
        return None
    contact = contacts[0]
    if not contact.member_id or not contact.subscribe or not contact.verified:
        return None
    member = _locked(Member.objects.filter(pk=contact.member_id), lock).first()
    if member is None:
        return None
    if not member.is_active:
        return None
    return contact


def retry_eligibility_for(campaign, raw_address, *, lock: bool = False) -> RetryEligibility | None:
    """Return the full retry eligibility, or ``None`` when any live requirement is absent.

    ``lock=True`` is used inside retry-draft creation so a concurrent contact/evidence edit cannot slip between the
    eligibility decision and the uniqueness-protected insert.
    """
    address = normalize_address(raw_address)
    if not address or len(address) > 254:
        return None
    row = _locked(BouncedAddress.objects.filter(address=address), lock).first()
    if (
        row is None
        or row.is_suppressed
        or row.complaint_count
        or row.ses_permanent_count
        or row.legacy_graph_permanent_review
        or row_has_graph_hold(row)
    ):
        return None
    contact = _unique_live_contact(address, lock=lock)
    if contact is None:
        return None
    # The source may have changed while a worker was waiting for provider admission.
    logs = RecipientLog.objects.annotate(normalized_address=Lower("email_address")).filter(
        campaign=campaign,
        campaign__retry_source_campaign__isnull=True,
        campaign__status__in=("sent", "partial", "failed"),
        normalized_address=address,
    )
    originals = list(_locked(logs, lock)[:2])
    if len(originals) != 1:
        return None
    original = originals[0]
    if not original.sent_at or original.member_id != contact.member_id:
        return None
    if original.status not in ("sent", "bounced", "rejected"):
        return None
    if has_unaggregated_permanent_or_complaint(address, lock=lock):
        return None
    categories = graph_campaign_categories(row, campaign, address, lock=lock)
    evidence_source = retryable_campaign_evidence(
        row, campaign, address, graph_categories=categories, source_log=original, lock=lock
    )
    if not evidence_source:
        return None
    return RetryEligibility(
        address=address,
        contact_email_id=contact.pk,
        member_id=contact.member_id,
        evidence_source=evidence_source,
        rejected_sender_provider=rejected_sender_provider(
            campaign, address, original, graph_categories=categories, lock=lock
        ),
    )


def retry_address_for(campaign, raw_address) -> str:
    """The normalized address only when it is currently safe to offer as a retry."""
    eligibility = retry_eligibility_for(campaign, raw_address)
    return eligibility.address if eligibility else ""


def assert_retry_campaign_eligible(campaign, *, recipient_log=None) -> RetryEligibility | None:
    """Recheck retry identity, one-address shape, live contact and evidence; ordinary campaigns return ``None``."""
    if not campaign.retry_source_campaign_id:
        return None
    try:
        campaign._enforce_retry_shape()
    except ValidationError as exc:
        raise RetryRefused("The retry audience no longer matches its locked address.") from exc
    if campaign.pk and (campaign.selected_members.exists() or campaign.exclude_members.exists()):
        raise RetryRefused("A retry cannot contain selected or excluded members.")
    eligibility = retry_eligibility_for(campaign.retry_source_campaign, campaign.retry_address)
    if eligibility is None:
        raise RetryRefused("The retry address is no longer eligible.")
    assert_alternate_retry_route(eligibility.rejected_sender_provider, campaign.retry_sending_provider)
    if campaign.status == "draft" and campaign.recipient_logs.exists():
        raise RetryRefused("A retry with prior delivery records cannot be queued again.")
    if recipient_log is not None:
        if campaign.recipient_logs.count() != 1:
            raise RetryRefused("A retry must have exactly one recipient log.")
        if normalize_address(recipient_log.email_address) != campaign.retry_address:
            raise RetryRefused("The retry recipient no longer matches its locked address.")
        if recipient_log.member_id != eligibility.member_id:
            raise RetryRefused("The retry recipient is no longer linked to the eligible contact.")
    successful_other = (
        EmailCampaign.objects.filter(
            retry_source_campaign_id=campaign.retry_source_campaign_id,
            retry_address=campaign.retry_address,
            recipient_logs__status__in=("sent", "delivered"),
        )
        .exclude(pk=campaign.pk)
        .exists()
    )
    if successful_other:
        raise RetryRefused("This source campaign/address has already been retried successfully.")
    return eligibility


def assert_retry_recipients(campaign, recipients, *, eligibility=None) -> None:
    """Require audience resolution itself to produce the one eligible linked contact."""
    if not campaign.retry_source_campaign_id:
        return
    eligibility = eligibility or assert_retry_campaign_eligible(campaign)
    if len(recipients) != 1:
        raise RetryRefused("A retry must resolve to exactly one recipient.")
    recipient = recipients[0]
    if normalize_address(recipient.get("email")) != campaign.retry_address:
        raise RetryRefused("The resolved retry recipient does not match its locked address.")
    if recipient.get("member_id") != eligibility.member_id:
        raise RetryRefused("The resolved retry recipient is no longer the eligible linked contact.")
