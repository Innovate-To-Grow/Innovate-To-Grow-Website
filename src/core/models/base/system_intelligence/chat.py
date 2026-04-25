import uuid

from django.conf import settings
from django.db import models


class ChatConversation(models.Model):
    """A single AI chat conversation thread."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, default="New Chat")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Chat Conversation"

    def __str__(self):
        return f"{self.title} ({self.created_by})"


class ChatMessage(models.Model):
    """A single message within a conversation."""

    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    model_id = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Model ID",
        help_text="The Bedrock model that produced this response (for audit).",
    )
    tool_calls = models.JSONField(
        default=list,
        blank=True,
        help_text="Bedrock tool invocations for this assistant turn (name, input, result preview).",
    )
    token_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text="Token consumption for this turn (inputTokens, outputTokens, totalTokens).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Chat Message"

    def __str__(self):
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return f"[{self.role}] {preview}"
