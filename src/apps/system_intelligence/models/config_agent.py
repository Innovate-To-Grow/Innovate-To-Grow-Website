"""The first fields of ``SystemIntelligenceConfig``: the config's name and active flag, the admin agent's model
settings, and which AI provider each role uses (blank = Amazon Bedrock). An abstract base, so the model keeps its fields in the same order: Django orders fields by
creation, and these are created before the model's own."""

from django.db import models

from apps.core.models import ProjectControlModel

DEFAULT_ROLE = "default"
PUBLIC_ROLE = "public"
PROVIDER_FIELDS = ("default_provider", "public_assistant_provider")
BEDROCK_HELP = "Blank uses Amazon Bedrock with the active AWS Credential Config."


class AdminAgentConfigFields(ProjectControlModel):
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
    default_provider = models.ForeignKey(
        "system_intelligence.LLMProviderConfig",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Default AI Provider",
        help_text=f"Provider of the Default AI Model (admin assistant, context summaries, scam review). {BEDROCK_HELP}",
    )
    default_model_id = models.CharField(
        max_length=256,
        blank=True,
        default="us.anthropic.claude-sonnet-4-20250514-v1:0",
        verbose_name="Default AI Model",
        help_text="Site-wide default model: a Bedrock model or inference profile ID, or the provider's model name.",
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

    public_assistant_provider = models.ForeignKey(
        "system_intelligence.LLMProviderConfig",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Public Assistant AI Provider",
        help_text="Provider of the Public Assistant Model (public chat and past-project AI search); used only when "
        f"that model is set, otherwise the default provider and model are used. {BEDROCK_HELP}",
    )

    class Meta:
        abstract = True

    def route_for(self, role: str = DEFAULT_ROLE):
        """The ``(provider, model_id)`` pair one role calls; ``provider`` is ``None`` for Amazon Bedrock."""
        if role == PUBLIC_ROLE and (self.public_assistant_model_id or "").strip():
            return self.public_assistant_provider, self.public_assistant_model_id
        return self.default_provider, self.default_model_id
