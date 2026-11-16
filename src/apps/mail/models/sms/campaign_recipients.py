"""One recipient of an SMS campaign and what happened to its text."""

from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel

from .campaign_options import SMS_LOG_STATUS_CHOICES


class SmsRecipientLog(ProjectControlModel):
    campaign = models.ForeignKey(
        "mail.SmsCampaign",
        on_delete=models.CASCADE,
        related_name="recipient_logs",
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    phone_number = models.CharField(max_length=20)
    recipient_name = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=16, choices=SMS_LOG_STATUS_CHOICES, default="pending")
    provider = models.CharField(max_length=16, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    sns_message_id = models.CharField(max_length=256, blank=True, default="", db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0, db_default=0)
    available_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    claimed_at = models.DateTimeField(null=True, blank=True, editable=False)
    uncertain_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "SMS Recipient Log"
        verbose_name_plural = "SMS Recipient Logs"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "phone_number"], name="unique_sms_campaign_recipient"),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.get_status_display()}"
