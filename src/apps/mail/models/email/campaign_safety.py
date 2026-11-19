"""Retry fields and model-level safety invariants for email campaigns."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models, router, transaction
from django.db.models.signals import m2m_changed

from apps.mail.redirects import is_safe_internal_redirect_path

RETRY_IMMUTABLE_FIELDS = (
    "retry_source_campaign_id",
    "retry_address",
    "retry_email_config_id",
    "retry_sending_provider",
    "retry_from_email",
    "retry_from_name",
    "retry_configuration_set",
    "audience_type",
    "event_id",
    "member_email_scope",
    "manual_emails",
    "exclude_audience_type",
    "exclude_member_email_scope",
    "exclude_event_id",
    "exclude_ticket_id",
)


def retry_constraints():
    """Database guards retained even when an older application image runs."""
    return [
        models.UniqueConstraint(
            fields=["retry_source_campaign", "retry_address"],
            condition=models.Q(retry_source_campaign__isnull=False),
            name="unique_email_retry_source_address",
        ),
        models.CheckConstraint(
            condition=models.Q(retry_source_campaign__isnull=True)
            | (
                models.Q(
                    audience_type="manual",
                    event__isnull=True,
                    exclude_audience_type="",
                    exclude_event__isnull=True,
                    exclude_ticket_id="",
                    retry_email_config__isnull=False,
                )
                & models.Q(manual_emails=models.F("retry_address"))
                & ~models.Q(retry_address="")
                & ~models.Q(retry_sending_provider="")
                & ~models.Q(retry_from_email="")
                & ~models.Q(retry_source_campaign=models.F("id"))
            ),
            name="email_retry_locked_shape",
        ),
    ]


class EmailCampaignSafetyMixin(models.Model):
    """Persist retry identity and validate both ordinary and retry campaign shapes."""

    retry_source_campaign = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retry_drafts",
        editable=False,
    )
    retry_address = models.CharField(max_length=254, blank=True, default="", db_default="", editable=False)
    retry_email_config = models.ForeignKey(
        "core.EmailServiceConfig",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="email_retry_drafts",
        editable=False,
    )
    retry_sending_provider = models.CharField(max_length=16, blank=True, default="", db_default="", editable=False)
    retry_from_email = models.CharField(max_length=254, blank=True, default="", db_default="", editable=False)
    retry_from_name = models.CharField(max_length=128, blank=True, default="", db_default="", editable=False)
    retry_configuration_set = models.CharField(max_length=255, blank=True, default="", db_default="", editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.subject[:200] if self.subject else "Untitled"
        if self.retry_source_campaign_id and not self._state.adding and self.status == "draft":
            # An editor holding an old draft must not overwrite a concurrent submission back to draft.
            db = kwargs.get("using") or router.db_for_write(type(self), instance=self)
            with transaction.atomic(using=db):
                self._enforce_retry_shape(lock_using=db)
                return super().save(*args, **kwargs)
        self._enforce_retry_shape()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not is_safe_internal_redirect_path(self.login_redirect_path):
            raise ValidationError({"login_redirect_path": "Please select a valid internal destination."})
        event_required_types = ("event_registrants", "ticket_type", "checked_in", "not_checked_in")
        if self.audience_type in event_required_types and not self.event_id:
            raise ValidationError(
                {"event": f"An event must be selected for the '{self.get_audience_type_display()}' audience."}
            )
        if self.audience_type == "ticket_type" and not self.manual_emails.strip():
            raise ValidationError({"manual_emails": "A ticket type must be selected."})
        if self.audience_type == "manual" and not self.manual_emails.strip():
            raise ValidationError({"manual_emails": "Please enter at least one email address."})
        try:
            self._enforce_retry_shape()
        except ValidationError as exc:
            raise ValidationError({"manual_emails": exc.messages}) from exc
        exclusion = (self.exclude_audience_type or "").strip()
        event_exclusions = ("event_registrants", "ticket_type", "checked_in", "not_checked_in")
        if exclusion in event_exclusions and not self.exclude_event_id:
            raise ValidationError({"exclude_event": "Select an event for this exclusion audience."})

    def _check_stored_retry(self, lock_using):
        if self._state.adding:
            return
        rows = type(self).objects.filter(pk=self.pk)
        if lock_using:
            rows = rows.using(lock_using).select_for_update()
        stored = rows.values(*RETRY_IMMUTABLE_FIELDS, "status").first()
        if not stored:
            return
        if bool(stored["retry_source_campaign_id"]) != bool(self.retry_source_campaign_id):
            raise ValidationError("An existing campaign cannot gain or lose retry provenance.")
        if not self.retry_source_campaign_id:
            return
        if self.status == "draft" and stored["status"] != "draft":
            raise ValidationError("A submitted retry cannot return to draft.")
        if any(getattr(self, field) != stored[field] for field in RETRY_IMMUTABLE_FIELDS):
            raise ValidationError("A retry campaign's address, audience and sending snapshot are immutable.")

    def _enforce_retry_shape(self, *, lock_using=None):
        """Keep a retry permanently bound to one normalized address and an empty exclusion."""
        self._check_stored_retry(lock_using)
        if not self.retry_source_campaign_id:
            return
        if self.retry_source_campaign_id == self.pk:
            raise ValidationError("A retry campaign cannot use itself as its source campaign.")
        if self._state.adding and self.status != "draft":
            raise ValidationError("A retry campaign must be created as a draft.")
        address = (self.retry_address or "").strip().lower()
        lines = [line.strip() for line in (self.manual_emails or "").splitlines() if line.strip()]
        if not address or len(lines) != 1:
            raise ValidationError("A retry campaign must contain exactly one email address.")
        try:
            validate_email(address)
            validate_email(lines[0])
        except ValidationError as exc:
            raise ValidationError("A retry campaign must contain one valid email address.") from exc
        if lines[0].lower() != address:
            raise ValidationError("A retry campaign's audience cannot differ from its retry address.")
        if self.audience_type != "manual":
            raise ValidationError("A retry campaign must use the Manual Emails audience.")
        if self.event_id or self.exclude_event_id or self.exclude_audience_type or self.exclude_ticket_id:
            raise ValidationError("A retry campaign cannot add or exclude another audience.")
        if not self.retry_email_config_id or not self.retry_sending_provider or not self.retry_from_email:
            raise ValidationError("A retry campaign must retain its reviewed sending method.")
        self.retry_address = self.manual_emails = address


def connect_retry_audience_guards(campaign_model) -> None:
    """Reject adding selected or excluded members to a provenance-bound retry."""

    def block_retry_audience_members(sender, instance, action, reverse, pk_set, **_kwargs):
        del sender
        if action != "pre_add":
            return
        if reverse:
            is_retry = (
                bool(pk_set)
                and campaign_model.objects.filter(pk__in=pk_set, retry_source_campaign__isnull=False).exists()
            )
        else:
            is_retry = bool(getattr(instance, "retry_source_campaign_id", None))
        if is_retry:
            raise ValidationError("A retry campaign cannot add selected or excluded members.")

    for sender, uid in (
        (campaign_model.selected_members.through, "mail_block_retry_selected_members"),
        (campaign_model.exclude_members.through, "mail_block_retry_exclude_members"),
    ):
        m2m_changed.connect(block_retry_audience_members, sender=sender, dispatch_uid=uid, weak=False)
