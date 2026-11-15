"""The site's SMS opt-out list (Mail → SMS Opt-outs): numbers no text may be sent to.

One row per number (E.164). It is active while ``cleared_at`` is empty. Rows come from three sources:

- **aws**: the sending number's opted-out list in AWS End User Messaging, read by the hourly sync (a person replied
  STOP, and AWS's own STOP handling put them there);
- **send_refusal**: AWS refused a send because the number opted out, learned before the next sync ran;
- **staff**: a person asked staff (by email, in person) to stop texting them.

The first two are cleared only by the sync, when AWS no longer lists the number (it replied START). Staff rows stay
until staff lift them. Every send path asks this list first (``core.services.aws.sms_opt_outs``), and the member's
contact phone is unsubscribed once (``contacts_unsubscribed_at``); clearing never subscribes anyone again.


``SmsOptOutSyncState`` is written only by the sync (``services.sms.policy.opt_out_sync``), with UPDATEs, never by a form,
so saving the settings can never overwrite what a running sync records.
"""

import uuid

from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel

SYNC_STATE_PK = uuid.UUID("00000000-0000-4000-8000-000000005302")


class SmsOptOutSyncState(ProjectControlModel):
    class Status(models.TextChoices):
        NEVER = "", "Not run yet"
        OK = "ok", "Up to date"
        PARTIAL = "partial", "Partly read (list longer than one run reads)"
        FAILED = "failed", "Failed"
        NOT_CONFIGURED = "not_configured", "SMS is not configured"
        DISABLED = "disabled", "Turned off"

    status = models.CharField(max_length=16, choices=Status.choices, blank=True, default="")
    message = models.CharField(max_length=300, blank=True, default="")
    list_name = models.CharField(max_length=128, blank=True, default="")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    listed_count = models.PositiveIntegerField(default=0)
    added_count = models.PositiveIntegerField(default=0)
    cleared_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "SMS opt-out sync state"
        verbose_name_plural = "SMS opt-out sync state"

    def __str__(self):
        return f"SMS opt-out sync ({self.get_status_display()})"

    @classmethod
    def load(cls) -> "SmsOptOutSyncState":
        obj, _created = cls.objects.get_or_create(pk=SYNC_STATE_PK)
        return obj


class SmsOptOut(ProjectControlModel):
    class Source(models.TextChoices):
        AWS = "aws", "AWS opt-out list (replied STOP)"
        SEND_REFUSAL = "send_refusal", "AWS refused a send (opted out)"
        STAFF = "staff", "Staff"

    phone_number = models.CharField(max_length=20, unique=True, help_text="E.164, for example +12095551234.")
    source = models.CharField(max_length=16, choices=Source.choices)
    opted_out_at = models.DateTimeField(help_text="When the number opted out (AWS's time when it gives one).")
    end_user_opted_out = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Opted out by the person",
        help_text="AWS's flag: yes when the person replied STOP, no when an AWS account admin added the number.",
    )
    last_seen_in_aws_at = models.DateTimeField(null=True, blank=True, verbose_name="Last seen in AWS's list")
    cleared_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Opted back in")
    cleared_reason = models.CharField(max_length=200, blank=True, default="")
    contacts_unsubscribed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Contact phones unsubscribed",
        help_text="When the members' matching phones were set to not subscribed (done once per opt-out).",
    )
    note = models.CharField(max_length=500, blank=True, default="", help_text="Why staff added it.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-opted_out_at"]
        verbose_name = "SMS opt-out"
        verbose_name_plural = "SMS opt-outs"

    def __str__(self):
        state = "opted out" if self.is_active else "opted back in"
        return f"{self.phone_number} ({state})"

    @property
    def is_active(self) -> bool:
        return self.cleared_at is None
