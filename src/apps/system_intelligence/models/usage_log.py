from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models.base.control import ProjectControlModel


class AssistantConversationLog(ProjectControlModel):
    """An audit-grouped record of a public-assistant or AI-search conversation.

    One row per logical conversation (grouped by a client-supplied
    ``session_id`` when present), holding denormalized counters. Individual
    turns live in the related ``AssistantMessageLog`` rows.
    """

    SOURCE_PUBLIC_CHAT = "public_chat"
    SOURCE_AI_SEARCH = "ai_search"
    SOURCE_CHOICES = [
        (SOURCE_PUBLIC_CHAT, "Public Chat"),
        (SOURCE_AI_SEARCH, "AI Search"),
    ]

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        db_index=True,
        help_text="Which audited endpoint produced this conversation.",
    )
    session_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Client-supplied conversation id (untrusted). Null for ungrouped turns.",
    )
    ip_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Salted SHA-256 hash of the visitor IP (never the raw IP).",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assistant_logs",
        help_text="Authenticated member, when the request was authenticated.",
    )
    message_count = models.PositiveIntegerField(
        default=0,
        help_text="Denormalized count of turns recorded in this conversation.",
    )
    total_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Denormalized sum of totalTokens across this conversation's turns.",
    )
    last_activity_at = models.DateTimeField(
        db_index=True,
        help_text="Timestamp of the most recent recorded turn.",
    )

    class Meta:
        ordering = ["-last_activity_at"]
        verbose_name = "Assistant Conversation Log"
        verbose_name_plural = "Assistant Conversation Logs"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "session_id"],
                condition=Q(session_id__isnull=False),
                name="uniq_assistant_log_source_session",
            )
        ]

    def __str__(self):
        return f"{self.get_source_display()} conversation ({self.message_count} turns)"


class AssistantMessageLog(ProjectControlModel):
    """A single recorded turn within an ``AssistantConversationLog``."""

    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_BUDGET = "budget"
    STATUS_UNAVAILABLE = "unavailable"
    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_ERROR, "Error"),
        (STATUS_BUDGET, "Budget exceeded"),
        (STATUS_UNAVAILABLE, "Unavailable"),
    ]

    conversation = models.ForeignKey(
        AssistantConversationLog,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    prompt = models.TextField(help_text="The visitor's question or search query.")
    reply = models.TextField(
        blank=True,
        default="",
        help_text="The assistant's reply text (empty for AI search).",
    )
    results = models.JSONField(
        default=list,
        blank=True,
        help_text="Compact result payload (e.g. AI-search project matches).",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        db_index=True,
        help_text="Terminal outcome of the turn.",
    )
    model_id = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Model ID",
        help_text="The Bedrock model/inference profile used for this turn.",
    )
    token_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text="Token consumption for this turn (inputTokens, outputTokens, totalTokens).",
    )
    latency_ms = models.PositiveIntegerField(
        default=0,
        help_text="Wall-clock latency of the model call in milliseconds.",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Assistant Message Log"
        verbose_name_plural = "Assistant Message Logs"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        preview = self.prompt[:60] + "..." if len(self.prompt) > 60 else self.prompt
        return f"[{self.status}] {preview}"
