"""What is recorded about bounced addresses besides the address itself: per-campaign counts, the actions staff took,
and the counting cursor."""

from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel


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

    bounced_address = models.ForeignKey("mail.BouncedAddress", on_delete=models.CASCADE, related_name="campaign_links")
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
        "mail.BouncedAddress", null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
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
