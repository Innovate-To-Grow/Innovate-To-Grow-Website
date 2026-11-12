"""Bounced addresses: one row per email address that ever bounced, its review state, the bulk-mail suppression staff
set on it, and the append-only log of what staff did (Mail → Delivery Operations → Email Monitoring → Bounced
addresses).

The counts come from the bounce records (``core.EmailBounce`` for Microsoft Graph reports, ``RecipientLog`` for
Amazon SES events) through ``apps.mail.services.email_monitoring.addresses.aggregate``. They are stored here, so they
outlive the bounce records' retention. Graph reports are counted by coarse classification and by category (what went
wrong); only a missing address or a disabled mailbox is evidence against the address. Counting never changes a member,
a contact email or a subscription: every change is an explicit staff action, recorded in ``BouncedAddressAction``.

``suppressed_at`` is the site's one bulk-mail suppression list: every campaign audience skips a suppressed address
(``apps.mail.services.suppression``). Transactional mail (sign-in codes, tickets, notifications) is never suppressed.
"""

from django.conf import settings
from django.db import models

from apps.core.models import EmailBounce, ProjectControlModel

Category = EmailBounce.Category
# The categories that count toward "repeated temporary failures" (with SES transient and undetermined bounces).
TEMPORARY_CATEGORIES = (Category.TRANSIENT, Category.MAILBOX_FULL, Category.UNKNOWN)
# Short labels for the counts column, in the order shown.
CATEGORY_SHORT_LABELS = {
    Category.HARD: "not found",
    Category.MAILBOX_DISABLED: "disabled",
    Category.MAILBOX_FULL: "full",
    Category.TRANSIENT: "temporary",
    Category.SPAM_REJECTED: "spam / reputation",
    Category.RELAY_DENIED: "relay denied",
    Category.POLICY_REJECTED: "policy",
    Category.DELAYED: "delayed",
    Category.UNKNOWN: "unknown",
}


class BouncedAddress(ProjectControlModel):
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

    # The suggestions about the address itself (the others point at our sending or at the recipient's policy).
    ADDRESS_SUGGESTIONS = frozenset(
        {Suggestion.UNSUBSCRIBE, Suggestion.UNDELIVERABLE, Suggestion.REPLACE, Suggestion.CONSIDER}
    )

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

    # Across both sources, for sorting and filtering.
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

    @property
    def is_suppressed(self) -> bool:
        return self.suppressed_at is not None

    @property
    def hard_total(self) -> int:
        return self.hard_count + self.ses_permanent_count

    @property
    def soft_total(self) -> int:
        return self.soft_count + self.ses_transient_count

    @property
    def unknown_total(self) -> int:
        return self.unknown_count + self.ses_undetermined_count

    def category_count(self, category: str) -> int:
        """How many Microsoft Graph reports of ``category`` were counted."""
        return int((self.category_counts or {}).get(category) or 0)

    @property
    def category_items(self) -> list[dict]:
        """The Graph reports by category, in a fixed order (categories with none left out)."""
        return [
            {"category": category, "label": short, "title": Category(category).label, "count": count}
            for category, short in CATEGORY_SHORT_LABELS.items()
            if (count := self.category_count(category))
        ]

    @property
    def temporary_total(self) -> int:
        """Temporary failures: Graph reports of a temporary, full-mailbox or unknown category, and SES transient and
        undetermined bounces. They only ever count toward "repeated temporary failures"."""
        graph = sum(self.category_count(category) for category in TEMPORARY_CATEGORIES)
        return graph + self.ses_transient_count + self.ses_undetermined_count

    @property
    def last_category_label(self) -> str:
        return dict(Category.choices).get(self.last_category, self.last_category)

    @property
    def last_category_guidance(self) -> str:
        return EmailBounce.guidance_for(self.last_category)

    @property
    def last_category_hint(self) -> str:
        return EmailBounce.hint_for(self.last_category)

    @property
    def suggests_address_action(self) -> bool:
        """Whether the suggestion is about the address itself (not our sending side or the recipient's policy)."""
        return self.suggestion in self.ADDRESS_SUGGESTIONS

    @property
    def has_matched_evidence(self) -> bool:
        """Whether a report matched an email the site sent, or an Amazon SES event (signed by AWS) names the address."""
        return bool(
            self.matched_count
            or self.ses_permanent_count
            or self.ses_transient_count
            or self.ses_undetermined_count
            or self.complaint_count
        )

    @property
    def graph_is_latest(self) -> bool:
        """Whether the latest event is a Microsoft Graph report (else an SES event, or nothing)."""
        if self.graph_last_at is None or not self.last_classification:
            return False
        return self.ses_last_at is None or self.graph_last_at >= self.ses_last_at

    @property
    def resolution_label(self) -> str:
        return dict(BouncedAddressAction.Action.choices).get(self.resolution, self.resolution)

    @property
    def report_total(self) -> int:
        """Every bounce and delay report and SES event counted for the address (complaints included)."""
        return (
            self.hard_total
            + self.soft_total
            + self.unknown_total
            + self.rejected_count
            + self.delayed_count
            + self.complaint_count
        )


class BouncedAddressCampaign(ProjectControlModel):
    """Which campaign a bounce came from: for Graph reports, exact (the matched email's campaign) or likely (the
    campaign that mailed the address shortly before); for SES, the campaign recipient log the event arrived on, with
    that event's details (one row per log, so recounting is idempotent)."""

    class Source(models.TextChoices):
        GRAPH = "graph", "Microsoft Graph report"
        SES = "ses", "Amazon SES event"

    class Match(models.TextChoices):
        EXACT = "exact", "Exact"
        LIKELY = "likely", "Likely"

    bounced_address = models.ForeignKey(BouncedAddress, on_delete=models.CASCADE, related_name="campaign_links")
    campaign_id = models.UUIDField(db_index=True)
    source = models.CharField(max_length=8, choices=Source.choices)
    match = models.CharField(max_length=8, choices=Match.choices, default=Match.EXACT)
    bounce_count = models.PositiveIntegerField(default=0)
    first_at = models.DateTimeField(null=True, blank=True)
    last_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ses_bounce_type = models.CharField(max_length=16, blank=True, default="")
    ses_bounce_subtype = models.CharField(max_length=32, blank=True, default="")
    ses_diagnostic = models.CharField(max_length=500, blank=True, default="")
    ses_bounced_at = models.DateTimeField(null=True, blank=True)
    ses_complained_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_at"]
        verbose_name = "Bounced Address Campaign"
        verbose_name_plural = "Bounced Address Campaigns"
        constraints = [
            models.UniqueConstraint(
                fields=["bounced_address", "campaign_id", "source"], name="unique_bounced_address_campaign_source"
            ),
        ]

    def __str__(self):
        return f"{self.bounced_address_id} in {self.campaign_id} ({self.source})"


class BouncedAddressAction(ProjectControlModel):
    """Append-only audit of every staff action on a bounced address. Snapshots keep it readable after the member,
    the actor or the contact email is deleted."""

    class Action(models.TextChoices):
        DISMISS = "dismiss", "Dismiss"
        REOPEN = "reopen", "Reopen"
        SUPPRESS = "suppress", "Suppress address"
        MARK_UNDELIVERABLE = "mark_undeliverable", "Mark undeliverable"
        CLEAR_SUPPRESSION = "clear_suppression", "Clear suppression"
        UNSUBSCRIBE = "unsubscribe", "Unsubscribe this address"
        MAKE_PRIMARY = "make_primary", "Use another address as primary"
        REPLACE = "replace", "Replace email"
        DELETE_EMAIL = "delete_email", "Delete this email address"
        DEACTIVATE = "deactivate", "Deactivate account"
        DELETE_ACCOUNT = "delete_account", "Delete account"
        REBUILD = "rebuild", "Rebuild counts from records"

    bounced_address = models.ForeignKey(
        BouncedAddress, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    address = models.CharField(max_length=254, blank=True, default="")
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_label = models.CharField(max_length=255, blank=True, default="")
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    member_ref = models.UUIDField(
        null=True, blank=True, help_text="The member's id, kept after the account is deleted."
    )
    member_name = models.CharField(max_length=255, blank=True, default="")
    role_before = models.CharField(max_length=16, blank=True, default="")
    role_after = models.CharField(max_length=16, blank=True, default="")
    note = models.CharField(max_length=500, blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bounced Address Action"
        verbose_name_plural = "Bounced Address Actions"

    def __str__(self):
        return f"{self.get_action_display()}: {self.address or 'all addresses'}"


class BounceAggregationState(ProjectControlModel):
    """Where counting stopped in one source (``graph``: bounce reports by creation; ``ses``: recipient logs by
    update), so each run continues from there and every report is counted once."""

    source = models.CharField(max_length=16, unique=True)
    cursor_at = models.DateTimeField(null=True, blank=True)
    cursor_id = models.UUIDField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    processed_total = models.PositiveBigIntegerField(default=0)

    class Meta:
        verbose_name = "Bounce Aggregation State"
        verbose_name_plural = "Bounce Aggregation States"

    def __str__(self):
        return f"Bounced-address counting: {self.source}"
