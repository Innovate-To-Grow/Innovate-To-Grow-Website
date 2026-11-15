"""Bounced addresses: one row per email address that ever bounced, its review state, the bulk-mail suppression staff
set on it, and the append-only log of what staff did (Mail → Delivery Operations → Email Monitoring → Bounced
addresses).

The counts come from the bounce records (``core.EmailBounce`` for Microsoft Graph reports, ``RecipientLog`` for
Amazon SES events) and from the helpdesk's "left the organisation" automatic replies that answer an email the site
sent (``core.InboundMessage``), through ``apps.mail.services.email_monitoring.addresses.aggregate``. They are stored
here, so they outlive the records' retention. Graph reports are counted by coarse classification and by category (what
went wrong); only a missing address or a disabled mailbox is evidence against the address on its own, and a
left-the-organisation notice is evidence to check (an out-of-office reply is never counted). Counting never changes a
member, a contact email or a subscription: every change is an explicit staff action, recorded in
``BouncedAddressAction``.

``suppressed_at`` is the site's one bulk-mail suppression list: every campaign audience skips a suppressed address
(``apps.mail.services.audience.suppression``). Transactional mail (sign-in codes, tickets, notifications) is never suppressed.
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
        CONSIDER = "consider", "Consider marking undeliverable (repeated temporary failures)"
        RELAY = "relay", "Our sending side: relay denied. Check our sending route and authorisation, not the address"
        REPUTATION = (
            "reputation",
            (
                "Our sending side: spam or reputation rejection. Check reputation, authentication and content, not the "
                "address"
            ),
        )
        POLICY = "policy", "Their server's policy refused the message, not the address: no action"
        LEFT_ORG = (
            "left_org",
            "May have left: an automatic reply says so. Check the notice, then replace the address or mark it "
            "undeliverable",
        )

    # The suggestions about the address itself (the others point at our sending or at the recipient's policy).
    ADDRESS_SUGGESTIONS = frozenset(
        {Suggestion.UNSUBSCRIBE, Suggestion.UNDELIVERABLE, Suggestion.REPLACE, Suggestion.LEFT_ORG, Suggestion.CONSIDER}
    )
    CONTACT_KINDS = {
        "new_address": "their new address, the notice says",
        "contact": "who to contact instead, the notice says",
        "mentioned": "an address the notice names",
    }

    address = models.CharField(max_length=254, unique=True, help_text="Lower-case address.")

    # Microsoft Graph bounce reports, each counted once (they are kept here after the reports are purged).
    hard_count = models.PositiveIntegerField(default=0)
    soft_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    delayed_count = models.PositiveIntegerField(default=0)
    unknown_count = models.PositiveIntegerField(default=0)
    # Of those, the reports matched to an email the site sent (exactly, or inferred from recipient and subject). Anyone
    # can mail the mailbox a report-shaped message, so an address with only unmatched reports is shown as such.
    matched_count = models.PositiveIntegerField(default=0)
    # The same reports by category ({category: count}; a category with no report is left out). Database defaults
    # too: the release before categories may still be counting while a deploy rolls out.
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
        help_text="The address the latest notice names instead (a hint from its text: never verified).",
    )
    left_org_contact_kind = models.CharField(max_length=16, blank=True, default="", db_default="")
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
