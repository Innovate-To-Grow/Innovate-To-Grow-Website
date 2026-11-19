"""Bounce evidence, staff review and bulk-mail holds for one normalized address.

Graph, SES and departure counts survive source retention. Staff actions are audited separately;
campaign holds never modify a contact, subscription or transactional email.
"""

from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel

from .bounced_address_summary import BouncedAddressSummaryMixin


class BouncedAddress(BouncedAddressSummaryMixin, ProjectControlModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DISMISSED = "dismissed", "Dismissed"
        RESOLVED = "resolved", "Resolved"

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        OTHER = "other", "Other"
        UNLINKED = "unlinked", "Unlinked contact"
        NONE = "none", "Not a contact"
        AMBIGUOUS = "ambiguous", "Ambiguous"

    class Suppression(models.TextChoices):
        UNDELIVERABLE = "undeliverable", "Marked undeliverable"
        SUPPRESSED = "suppressed", "Suppressed"

    class Suggestion(models.TextChoices):
        UNSUBSCRIBE = "unsubscribe", "Unsubscribe: they reported us as spam"
        UNDELIVERABLE = "undeliverable", "Mark undeliverable or replace the address"
        REPLACE = "replace", "Replace the address (the mailbox is disabled), or mark it undeliverable"
        CONSIDER = "consider", "Repeated temporary failures: check the receiving service, then retry this address"
        RELAY = (
            "relay",
            "Our sending side: relay denied. Check our sending route and authorisation, then retry from another "
            "configured sender; the problem is not the address",
        )
        REPUTATION = (
            "reputation",
            (
                "Our sending side: spam or reputation rejection. Check reputation, authentication and content, then "
                "retry from another configured sender; the problem is not the address"
            ),
        )
        POLICY = "policy", "Their server's policy refused the message, not the address: no action"
        VERIFY_EVIDENCE = "verify_evidence", "Review the evidence before taking action on this address"
        SES_HOLD = "ses_hold", "SES has stopped delivery. Check its suppression, subscription or bounce details"
        FIX_CONTENT = "fix_content", "Review the rejected message size, content or attachment before sending"
        LEFT_ORG = (
            "left_org",
            "May have left: an automatic reply says so. Check the notice, then replace the address or mark it "
            "undeliverable",
        )

    # Suggestions involving the address itself (including a manual retry after a receiving-side failure).
    ADDRESS_SUGGESTIONS = frozenset(
        {
            Suggestion.UNSUBSCRIBE,
            Suggestion.UNDELIVERABLE,
            Suggestion.REPLACE,
            Suggestion.LEFT_ORG,
            Suggestion.CONSIDER,
            Suggestion.VERIFY_EVIDENCE,
        }
    )
    trusted_graph_hard_count = models.PositiveIntegerField(default=0, db_default=0)
    trusted_graph_disabled_count = models.PositiveIntegerField(default=0, db_default=0)
    trusted_graph_last_permanent_at = models.DateTimeField(null=True, blank=True)
    graph_hold_cleared_at = models.DateTimeField(null=True, blank=True)
    legacy_graph_permanent_review = models.BooleanField(default=False, db_default=False)

    address = models.CharField(max_length=254, unique=True, help_text="Lower-case address.")

    hard_count = models.PositiveIntegerField(default=0)
    soft_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    delayed_count = models.PositiveIntegerField(default=0)
    unknown_count = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    category_counts = models.JSONField(
        default=dict,
        db_default={},
        blank=True,
        help_text="Microsoft Graph reports by category (what went wrong), each counted once.",
    )
    graph_first_at = models.DateTimeField(null=True, blank=True)
    graph_last_at = models.DateTimeField(null=True, blank=True)
    last_classification = models.CharField(max_length=16, blank=True, default="")
    last_category = models.CharField(max_length=24, blank=True, default="", db_default="")
    last_status_code = models.CharField(max_length=16, blank=True, default="")
    last_reason = models.CharField(max_length=255, blank=True, default="")
    last_diagnostic = models.CharField(max_length=1000, blank=True, default="")
    last_remote_mta = models.CharField(max_length=255, blank=True, default="")

    # Amazon SES events, one per campaign recipient log (recounted from ``BouncedAddressCampaign``).
    ses_permanent_count = models.PositiveIntegerField(default=0)
    ses_transient_count = models.PositiveIntegerField(default=0)
    ses_undetermined_count = models.PositiveIntegerField(default=0)
    complaint_count = models.PositiveIntegerField(default=0)
    ses_first_at = models.DateTimeField(null=True, blank=True)
    ses_last_at = models.DateTimeField(null=True, blank=True)
    ses_last = models.JSONField(default=dict, blank=True)

    # "Left the organisation" automatic replies (the person left, retired or changed address) that answer an email the
    # site sent to this address, each counted once. Evidence to check, never applied; an out-of-office reply is never
    # counted. Database defaults: the release before may still save rows while a deploy rolls out.
    left_org_count = models.PositiveIntegerField(
        default=0,
        db_default=0,
        help_text="Automatic replies to the site's mail saying the person left or the address changed.",
    )
    left_org_first_at = models.DateTimeField(null=True, blank=True)
    left_org_last_at = models.DateTimeField(null=True, blank=True)
    left_org_contact = models.CharField(
        max_length=254,
        blank=True,
        default="",
        db_default="",
        help_text="The address the latest notice names instead (unverified and retained only for the review period).",
    )
    left_org_contact_kind = models.CharField(max_length=16, blank=True, default="", db_default="")
    left_org_contact_name = models.CharField(
        max_length=100, blank=True, default="", db_default="", help_text="Unverified name in the latest notice."
    )
    left_org_contact_phone = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_default="",
        help_text="Unverified US phone in the latest notice, retained only for the bounded hint-review period.",
    )
    # Address, name and phone are third-party PII copied from the latest source message. The source and expiry make
    # that copy temporary; deleting the source clears all hints while the aggregate notice evidence remains.
    left_org_hint_source = models.ForeignKey(
        "core.InboundMessage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Inbound message that supplied the retained unverified contact hints.",
    )
    left_org_hint_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the unverified contact hints must be cleared.",
    )
    left_org_ticket = models.PositiveIntegerField(
        null=True, blank=True, help_text="The helpdesk ticket that holds the latest notice."
    )

    # Across every source, for sorting and filtering.
    first_bounce_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_bounce_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Review state: only queue state, never member data.
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolution = models.CharField(max_length=32, blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True, default="")

    # Bulk-mail suppression (campaigns skip the address while ``suppressed_at`` is set).
    suppression = models.CharField(max_length=16, choices=Suppression.choices, blank=True, default="")
    suppressed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    suppressed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    suppressed_reason = models.CharField(max_length=500, blank=True, default="")

    # Cached for filtering, refreshed when counting and on every page; every page and action re-checks them live.
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.NONE, db_index=True)
    contact_email = models.ForeignKey(
        "authn.ContactEmail", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    suggestion = models.CharField(max_length=16, choices=Suggestion.choices, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-last_bounce_at"]
        verbose_name = "Bounced Address"
        verbose_name_plural = "Bounced Addresses"

    def __str__(self):
        return self.address
