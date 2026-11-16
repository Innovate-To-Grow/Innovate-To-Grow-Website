"""The System Intelligence configuration form."""

import logging

from django import forms
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget

from apps.system_intelligence.models import SystemIntelligenceConfig

logger = logging.getLogger(__name__)


class SystemIntelligenceConfigForm(forms.ModelForm):
    default_model_id = forms.TypedChoiceField(
        coerce=str,
        required=False,
        label="Default AI Model",
        help_text="Site-wide default Bedrock model or inference profile ID.",
        widget=UnfoldAdminSelectWidget,
    )
    public_assistant_model_id = forms.TypedChoiceField(
        coerce=str,
        required=False,
        label="Public Assistant Model",
        help_text="Bedrock model/inference profile ID for the public assistant. Falls back to the Default AI Model.",
        widget=UnfoldAdminSelectWidget,
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
        self._populate_model_choices("default_model_id", empty_label="---------")
        self._populate_model_choices("public_assistant_model_id", empty_label="Use Default AI Model")

    def _populate_model_choices(self, field_name, *, empty_label):
        """Populate a model-id field with the live Bedrock catalog, grouped by provider."""
        current = self.initial.get(field_name, "") or getattr(self.instance, field_name, "") or ""
        try:
            from apps.system_intelligence.services.bedrock import get_available_models

            grouped = get_available_models()
            choices = [("", empty_label)]
            seen_model_ids = set()
            for group, models in grouped:
                seen_model_ids.update(model_id for model_id, _name in models)
                choices.append((group, list(models)))
            if current and current not in seen_model_ids:
                choices.append(("Configured Model", [(current, current)]))
            self.fields[field_name].choices = choices
        except Exception:
            logger.debug("Could not fetch Bedrock models for System Intelligence config choices", exc_info=True)
            if current:
                self.fields[field_name].choices = [("", empty_label), (current, current)]
            else:
                self.fields[field_name].choices = [("", empty_label)]
