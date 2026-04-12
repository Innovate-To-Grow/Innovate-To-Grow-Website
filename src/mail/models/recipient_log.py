from django.conf import settings
from django.db import models

from core.models import ProjectControlModel

DELIVERY_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("sent", "Sent"),
    ("failed", "Failed"),
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

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Recipient Log"
        verbose_name_plural = "Recipient Logs"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "email_address"], name="unique_campaign_recipient"),
        ]

    def __str__(self):
        return f"{self.email_address} — {self.get_status_display()}"
