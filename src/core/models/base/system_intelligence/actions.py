import uuid

from django.conf import settings
from django.db import models

from .chat import ChatConversation, ChatMessage


class SystemIntelligenceActionRequest(models.Model):
    """A human-approved write action proposed by System Intelligence."""

    ACTION_CMS_PAGE_UPDATE = "cms_page_update"
    ACTION_DB_CREATE = "db_create"
    ACTION_DB_UPDATE = "db_update"
    ACTION_DB_DELETE = "db_delete"
    ACTION_CHOICES = [
        (ACTION_CMS_PAGE_UPDATE, "CMS page update"),
        (ACTION_DB_CREATE, "Database create"),
        (ACTION_DB_UPDATE, "Database update"),
        (ACTION_DB_DELETE, "Database delete"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPLIED = "applied"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="action_requests",
    )
    assistant_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_requests",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_intelligence_action_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_system_intelligence_action_requests",
    )
    action_type = models.CharField(max_length=32, choices=ACTION_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    target_app_label = models.CharField(max_length=100, blank=True, default="")
    target_model = models.CharField(max_length=100, blank=True, default="")
    target_pk = models.CharField(max_length=128, blank=True, default="")
    target_repr = models.CharField(max_length=300, blank=True, default="")
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)
    diff = models.JSONField(default=list, blank=True)
    preview_token = models.CharField(max_length=64, blank=True, default="")
    preview_url = models.URLField(max_length=1000, blank=True, default="")
    preview_expires_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "System Intelligence Action Request"
        verbose_name_plural = "System Intelligence Action Requests"
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()}: {self.title} [{self.status}]"
