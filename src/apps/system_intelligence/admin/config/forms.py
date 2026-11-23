"""The System Intelligence configuration form.

Each role (Default, Public Assistant) picks a provider and a model name. With no provider the model must be in the
live Bedrock catalog (when the catalog can be read); with an AI provider any model name the provider serves is
accepted. The model inputs suggest Bedrock catalog entries and the configured providers' known model names.
"""

import logging

from django import forms
from unfold.widgets import UnfoldAdminTextareaWidget

from apps.system_intelligence.models import LLMProviderConfig, SystemIntelligenceConfig
from apps.system_intelligence.services.agents.providers.presets import suggested_models

from .provider_forms import ModelIdInput

logger = logging.getLogger(__name__)

MODEL_PAIRS = (("default_model_id", "default_provider"), ("public_assistant_model_id", "public_assistant_provider"))
NOT_IN_BEDROCK = "This is not an available Bedrock model. Select an AI provider for non-Bedrock models."
MODEL_REQUIRED = "Enter the model this AI provider should use."


class SystemIntelligenceConfigForm(forms.ModelForm):
    default_model_id = forms.CharField(
        required=False,
        max_length=256,
        label="Default AI Model",
        help_text="Bedrock model or inference profile ID, or the model name of the Default AI Provider "
        "(e.g. deepseek-chat, kimi-k2-0905-preview).",
    )
    public_assistant_model_id = forms.CharField(
        required=False,
        max_length=256,
        label="Public Assistant Model",
        help_text="Model of the Public Assistant AI Provider (Bedrock when that is blank). Blank uses the Default AI "
        "Provider and Model.",
    )

    class Meta:
        model = SystemIntelligenceConfig
        fields = "__all__"
        widgets = {
            "system_prompt": UnfoldAdminTextareaWidget(attrs={"rows": 8}),
            "public_assistant_system_prompt": UnfoldAdminTextareaWidget(attrs={"rows": 8}),
            "public_assistant_unavailable_message": UnfoldAdminTextareaWidget(attrs={"rows": 3}),
            "public_assistant_welcome_message": UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bedrock_ids = None
        suggestions = self._bedrock_suggestions() + self._provider_suggestions()
        for model_field, _provider_field in MODEL_PAIRS:
            self.fields[model_field].widget = ModelIdInput(suggestions=suggestions)

    def _bedrock_suggestions(self):
        """Live Bedrock catalog as ``(model_id, "Group · Name")``; empty (and no catalog check) if unreadable."""
        try:
            from apps.system_intelligence.services.bedrock import get_available_models

            grouped = get_available_models()
        except Exception:
            logger.debug("Could not fetch Bedrock models for System Intelligence config choices", exc_info=True)
            return []
        entries = [(model_id, f"Bedrock · {group} · {name}") for group, models in grouped for model_id, name in models]
        self._bedrock_ids = {model_id for model_id, _label in entries} or None
        return entries

    def _provider_suggestions(self):
        entries, seen = [], set()
        for provider in LLMProviderConfig.objects.order_by("name"):
            for name in suggested_models(provider.preset):
                if (provider.pk, name) not in seen:
                    seen.add((provider.pk, name))
                    entries.append((name, f"{provider.name} · {name}"))
        return entries

    def clean(self):
        cleaned = super().clean()
        for model_field, provider_field in MODEL_PAIRS:
            model_id = (cleaned.get(model_field) or "").strip()
            cleaned[model_field] = model_id
            # A read-only provider field (non-superuser staff) is not on the form: keep the saved provider.
            provider = (
                cleaned.get(provider_field) if provider_field in self.fields else getattr(self.instance, provider_field)
            )
            unchanged = model_id == (self.initial.get(model_field) or "") and provider_field not in self.changed_data
            if provider is None:
                if model_id and self._bedrock_ids is not None and model_id not in self._bedrock_ids and not unchanged:
                    self.add_error(model_field, NOT_IN_BEDROCK)
            elif not model_id and model_field == "default_model_id":
                self.add_error(model_field, MODEL_REQUIRED)
        return cleaned
