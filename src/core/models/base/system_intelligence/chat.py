from django.conf import settings
from django.db import models

from ..control import ProjectControlModel


class ChatConversation(ProjectControlModel):
    """A single AI chat conversation thread."""

    MODE_NORMAL = "normal"
    MODE_PLAN = "plan"
    MODE_CHOICES = [(MODE_NORMAL, "Normal"), (MODE_PLAN, "Plan-only")]

    title = models.CharField(max_length=200, default="New Chat")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_conversations",
    )
    mode = models.CharField(
        max_length=16,
        choices=MODE_CHOICES,
        default=MODE_NORMAL,
        help_text="Plan mode disables write tools and steers the agent toward planning only.",
    )
    context_summary = models.TextField(
        blank=True,
        default="",
        help_text="Rolling summary of older System Intelligence conversation context.",
    )
    context_summary_updated_at = models.DateTimeField(null=True, blank=True)
    context_summary_through_message = models.ForeignKey(
        "ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Newest message included in the rolling context summary.",
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Chat Conversation"

    def __str__(self):
        return f"{self.title} ({self.created_by})"


class ChatMessage(ProjectControlModel):
    """A single message within a conversation."""

    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]

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
    context_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text="Estimated context prepared for this turn before invoking the model.",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Chat Message"

    def __str__(self):
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return f"[{self.role}] {preview}"
