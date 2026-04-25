from django.db import models


class SystemIntelligenceConfig(models.Model):
    """System Intelligence configuration for Amazon Bedrock."""

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
        return f"{self.name}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            SystemIntelligenceConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def is_configured(self):
        return True
