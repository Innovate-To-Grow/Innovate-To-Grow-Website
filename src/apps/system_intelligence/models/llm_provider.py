"""An AI provider System Intelligence can call besides Amazon Bedrock: any OpenAI-compatible Chat Completions API
(OpenAI, DeepSeek, Kimi / Moonshot AI, a gateway) or an Anthropic Messages API (Anthropic, or the Anthropic-format
endpoints DeepSeek and Kimi also offer).

The API key never lives in this table: it is kept in the credential store (AWS Secrets Manager in production) and the
row keeps only a pointer to the pinned stored version plus the key's last four characters. Keys are installed and
removed on their own admin pages (``admin/config/provider_keys``).
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ProjectControlModel

DISABLED_NEEDS_KEY = "Install an API key before enabling this provider."
TIMEOUT_RANGE = (5, 600)
CONTEXT_WINDOW_MAX = 10_000_000
ENDPOINT_RESET_FIELDS = ("key_secret_ref", "key_version_id", "key_hint", "key_installed_at", "is_enabled")


class LLMProviderConfig(ProjectControlModel):
    class ApiFormat(models.TextChoices):
        OPENAI = "openai", "OpenAI-compatible (Chat Completions)"
        ANTHROPIC = "anthropic", "Anthropic Messages"

    class Preset(models.TextChoices):
        OPENAI = "openai", "OpenAI"
        DEEPSEEK = "deepseek", "DeepSeek (OpenAI format)"
        DEEPSEEK_ANTHROPIC = "deepseek_anthropic", "DeepSeek (Anthropic format)"
        MOONSHOT = "moonshot", "Kimi / Moonshot AI, global (OpenAI format)"
        MOONSHOT_CN = "moonshot_cn", "Kimi / Moonshot AI, China (OpenAI format)"
        MOONSHOT_ANTHROPIC = "moonshot_anthropic", "Kimi / Moonshot AI (Anthropic format)"
        ANTHROPIC = "anthropic", "Anthropic"
        CUSTOM = "custom", "Custom endpoint"

    name = models.CharField(max_length=128, unique=True, verbose_name="Provider Name")
    preset = models.CharField(
        max_length=32,
        choices=Preset.choices,
        default=Preset.DEEPSEEK,
        verbose_name="Provider",
        help_text="A known provider fixes the API format and base URL. Choose Custom endpoint for any other "
        "OpenAI-compatible or Anthropic-format API.",
    )
    api_format = models.CharField(
        max_length=16,
        choices=ApiFormat.choices,
        default=ApiFormat.OPENAI,
        verbose_name="API Format",
        help_text="Used for Custom endpoint only; a known provider sets it.",
    )
    base_url = models.CharField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="Base URL",
        help_text="Custom endpoint only, e.g. https://gateway.example.com/v1. Must be https and resolve to a public "
        "address. OpenAI format appends /chat/completions, Anthropic format appends /v1/messages.",
    )
    is_enabled = models.BooleanField(
        default=False,
        verbose_name="Enabled",
        help_text="A disabled provider is never called; System Intelligence features that use it report unavailable.",
    )
    request_timeout_seconds = models.PositiveIntegerField(
        default=120,
        verbose_name="Request Timeout (seconds)",
        help_text="How long one model call may take before it is abandoned.",
    )
    context_window_tokens = models.PositiveIntegerField(
        default=0,
        verbose_name="Context Window (tokens)",
        help_text="Input context window of the models used through this provider. 0 looks it up in LiteLLM's model "
        "list and otherwise assumes a conservative 64,000.",
    )
    key_secret_ref = models.CharField(max_length=512, blank=True, default="", editable=False)
    key_version_id = models.CharField(max_length=64, blank=True, default="", editable=False)
    key_hint = models.CharField(max_length=8, blank=True, default="", editable=False, verbose_name="Key Ends With")
    key_installed_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Key Installed")

    class Meta:
        verbose_name = "AI Provider"
        verbose_name_plural = "AI Providers"
        ordering = ("name",)

    def __str__(self):
        state = "" if self.is_enabled else " (disabled)"
        return f"{self.name}{state}"

    @property
    def key_configured(self) -> bool:
        return bool(self.key_secret_ref and self.key_version_id)

    @property
    def is_custom(self) -> bool:
        return self.preset == self.Preset.CUSTOM

    @property
    def effective_api_format(self) -> str:
        from apps.system_intelligence.services.agents.providers.presets import PRESETS

        preset = PRESETS.get(self.preset)
        return preset.api_format if preset else self.api_format

    @property
    def effective_base_url(self) -> str:
        from apps.system_intelligence.services.agents.providers.presets import PRESETS

        preset = PRESETS.get(self.preset)
        return preset.base_url if preset else self.base_url

    def save(self, *args, **kwargs):
        """An installed key belongs to the endpoint it was installed for: moving the provider to another endpoint
        unpins the key and disables the provider, so a stored key is never sent to a host it was not meant for."""
        if not self._state.adding and self.key_configured:
            previous = type(self).objects.filter(pk=self.pk).values("preset", "api_format", "base_url").first()
            if previous and previous != {
                "preset": self.preset,
                "api_format": self.api_format,
                "base_url": self.base_url,
            }:
                self.key_secret_ref = self.key_version_id = self.key_hint = ""  # nosec B105 - clears a store pointer, not a password
                self.key_installed_at = None
                self.is_enabled = False
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = {*kwargs["update_fields"], *ENDPOINT_RESET_FIELDS}
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        from apps.system_intelligence.services.agents.providers.endpoints import EndpointError, validate_base_url
        from apps.system_intelligence.services.agents.providers.presets import PRESETS

        errors = {}
        preset = PRESETS.get(self.preset)
        if preset is not None:
            self.api_format = preset.api_format
            self.base_url = ""
        else:
            try:
                self.base_url = validate_base_url(self.base_url)
            except EndpointError as exc:
                errors["base_url"] = str(exc)
        if self.is_enabled and not self.key_configured:
            errors["is_enabled"] = DISABLED_NEEDS_KEY
        low, high = TIMEOUT_RANGE
        if not low <= (self.request_timeout_seconds or 0) <= high:
            errors["request_timeout_seconds"] = f"Must be between {low} and {high} seconds."
        if (self.context_window_tokens or 0) > CONTEXT_WINDOW_MAX:
            errors["context_window_tokens"] = f"Must be at most {CONTEXT_WINDOW_MAX:,}."
        if errors:
            raise ValidationError(errors)
