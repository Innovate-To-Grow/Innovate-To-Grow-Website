from django.conf import settings
from django.db import models

from core.models import ProjectControlModel

from .model_accounts import GoogleAccount, SESAccount


class EmailLog(ProjectControlModel):
    """Audit log for Gmail API operations performed through the admin."""

    class Action(models.TextChoices):
        SEND = "send", "Send"
        REPLY = "reply", "Reply"
        FORWARD = "forward", "Forward"
        READ = "read", "Read"
        DELETE = "delete", "Delete"
        LABEL = "label", "Label"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    account = models.ForeignKey(
        GoogleAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_logs"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    gmail_message_id = models.CharField(max_length=255, blank=True, default="")
    subject = models.CharField(max_length=500, blank=True, default="")
    recipients = models.TextField(blank=True, default="", help_text="Comma-separated list of recipients.")
    error_message = models.TextField(blank=True, default="")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mail_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email Log"
        verbose_name_plural = "Email Logs"
        indexes = [models.Index(fields=["action", "status"]), models.Index(fields=["account", "created_at"])]

    def __str__(self):
        return f"{self.get_action_display()} - {self.subject[:50] or '(no subject)'}"


class SESEmailLog(ProjectControlModel):
    """Audit log for SES sends performed through the admin."""

    class Action(models.TextChoices):
        SEND = "send", "Send"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Complained"

    account = models.ForeignKey(SESAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_logs")
    action = models.CharField(max_length=10, choices=Action.choices, default=Action.SEND)
    status = models.CharField(max_length=10, choices=Status.choices)
    ses_message_id = models.CharField(max_length=255, blank=True, default="")
    subject = models.CharField(max_length=500, blank=True, default="")
    recipients = models.TextField(blank=True, default="", help_text="Comma-separated list of recipients.")
    error_message = models.TextField(blank=True, default="")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ses_mail_logs",
    )
    delivery_status = models.CharField(
        max_length=12,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )
    delivery_timestamp = models.DateTimeField(null=True, blank=True)
    bounce_type = models.CharField(max_length=30, blank=True, default="")
    bounce_subtype = models.CharField(max_length=30, blank=True, default="")
    complaint_feedback_type = models.CharField(max_length=30, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SES Email Log"
        verbose_name_plural = "SES Email Logs"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["ses_message_id"]),
            models.Index(fields=["delivery_status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.subject[:50] or '(no subject)'}"
