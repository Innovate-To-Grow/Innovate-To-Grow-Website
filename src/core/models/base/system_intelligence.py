import uuid

from django.conf import settings
from django.db import models


class SystemIntelligenceConfig(models.Model):
    """
    System Intelligence configuration for Amazon Bedrock.

    Stores the Bedrock model identifier, system prompt, and generation
    parameters. Multiple configs can exist but only one may be active
    at a time. Managed via Django admin under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration.",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )

    model_id = models.CharField(
        max_length=256,
        default="us.anthropic.claude-sonnet-4-20250514-v1:0",
        verbose_name="Bedrock Model",
        help_text="Model or inference profile ID to use for AI chat.",
    )
    system_prompt = models.TextField(
        blank=True,
        default=(
            "You are a helpful AI assistant for the Innovate to Grow admin team. "
            "You have access to the application database and can query members, events, "
            "registrations, projects, email campaigns, CMS pages, news articles, and "
            "analytics data. Use the available tools to look up data when answering "
            "questions. Always verify facts by querying the database rather than guessing."
        ),
        verbose_name="System Prompt",
    )
    max_tokens = models.PositiveIntegerField(
        default=4096,
        verbose_name="Max Tokens",
        help_text="Maximum number of tokens in the model response.",
    )
    temperature = models.FloatField(
        default=0.7,
        verbose_name="Temperature",
        help_text="Sampling temperature (0.0 = deterministic, 1.0 = creative).",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Intelligence Config"
        verbose_name_plural = "System Intelligence Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        return f"{self.name}: {self.model_id}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            SystemIntelligenceConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config, falling back to the most recently updated one."""
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def is_configured(self):
        return bool(self.model_id)


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

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Chat Message"

    def __str__(self):
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return f"[{self.role}] {preview}"
