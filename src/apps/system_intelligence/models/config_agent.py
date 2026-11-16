"""The first fields of ``SystemIntelligenceConfig``: the config's name and active flag, and the admin agent's
Bedrock model settings. An abstract base, so the model keeps its fields in the same order: Django orders fields by
creation, and these are created before the model's own."""

from django.db import models

from apps.core.models import ProjectControlModel


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
    default_model_id = models.CharField(
        max_length=256,
        blank=True,
        default="us.anthropic.claude-sonnet-4-20250514-v1:0",
        verbose_name="Default AI Model",
        help_text="Site-wide default Bedrock model or inference profile ID.",
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

    class Meta:
        abstract = True
