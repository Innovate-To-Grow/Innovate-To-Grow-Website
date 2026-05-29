from django.conf import settings
from django.db import models

from core.models import ProjectControlModel

DELIVERY_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("sent", "Sent"),
    ("delivered", "Delivered"),
    ("bounced", "Bounced"),
    ("complained", "Complained"),
    ("rejected", "Rejected"),
    ("failed", "Failed"),
]

BOUNCE_TYPE_CHOICES = [
    ("", ""),
    ("Permanent", "Permanent"),
    ("Transient", "Transient"),
    ("Undetermined", "Undetermined"),
]


class RecipientLog(ProjectControlModel):
    campaign = models.ForeignKey(
        "mail.EmailCampaign",
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
    email_address = models.EmailField()
    recipient_name = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=16, choices=DELIVERY_STATUS_CHOICES, default="pending")
    provider = models.CharField(max_length=16, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)

    # SES async event tracking
    ses_message_id = models.CharField(max_length=256, blank=True, default="", db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    complained_at = models.DateTimeField(null=True, blank=True)
    bounce_type = models.CharField(max_length=16, blank=True, default="", choices=BOUNCE_TYPE_CHOICES)
    bounce_subtype = models.CharField(max_length=32, blank=True, default="")
    diagnostic_code = models.TextField(blank=True, default="")
    complaint_feedback_type = models.CharField(max_length=32, blank=True, default="")
    last_event_type = models.CharField(max_length=32, blank=True, default="")
    last_event_at = models.DateTimeField(null=True, blank=True)
    last_sns_message_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Recipient Log"
        verbose_name_plural = "Recipient Logs"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "email_address"], name="unique_campaign_recipient"),
        ]

    def __str__(self):
        return f"{self.email_address} — {self.get_status_display()}"
