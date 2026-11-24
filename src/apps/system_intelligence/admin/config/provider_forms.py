"""Forms for the AI provider key pages and the connection test, plus the model-name input with suggestions.

The key form is a plain form on its own admin page, never part of the provider's change form, so the confirm-on-save
step never stashes a key in the session or cache. The key box never renders a value back.
"""

from django import forms
from django.utils.html import format_html, format_html_join
from django.views.decorators.debug import sensitive_variables
from unfold.widgets import UnfoldAdminPasswordWidget, UnfoldAdminTextInputWidget

from apps.system_intelligence.services.agents.providers.keys import ProviderKeyError, validate_api_key

API_KEY_FIELD = "api_key"


class InstallApiKeyForm(forms.Form):
    api_key = forms.CharField(
        label="API key",
        strip=True,
        max_length=1024,
        help_text="Stored in the credential store (AWS Secrets Manager in production) and never shown again. "
        "Installing a key replaces the current one.",
        widget=UnfoldAdminPasswordWidget(render_value=False, attrs={"autocomplete": "new-password"}),
    )

    @sensitive_variables()
    def clean_api_key(self):
        try:
            return validate_api_key(self.cleaned_data.get(API_KEY_FIELD))
        except ProviderKeyError as exc:
            raise forms.ValidationError(str(exc)) from None


class RemoveApiKeyForm(forms.Form):
    confirm = forms.BooleanField(
        label="Remove the key and disable this provider",
        help_text="Features that use this provider report unavailable until a new key is installed and it is enabled.",
    )


class TestConnectionForm(forms.Form):
    model_id = forms.CharField(
        label="Model",
        max_length=256,
        help_text="One short request (at most 16 output tokens) is sent to this model.",
    )

    def __init__(self, *args, suggestions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["model_id"].widget = ModelIdInput(suggestions=[(name, name) for name in suggestions])


class ModelIdInput(UnfoldAdminTextInputWidget):
    """A free-text model name with a ``<datalist>`` of suggestions (Bedrock catalog entries, provider presets)."""

    def __init__(self, attrs=None, suggestions=()):
        super().__init__(attrs={"autocomplete": "off", "spellcheck": "false", **(attrs or {})})
        self.suggestions = list(suggestions)

    def render(self, name, value, attrs=None, renderer=None):
        list_id = f"{(attrs or {}).get('id') or 'id_' + name}_suggestions"
        html = super().render(name, value, {**(attrs or {}), "list": list_id}, renderer)
        options = format_html_join("", '<option value="{}">{}</option>', self.suggestions)
        return format_html('{}<datalist id="{}">{}</datalist>', html, list_id, options)
