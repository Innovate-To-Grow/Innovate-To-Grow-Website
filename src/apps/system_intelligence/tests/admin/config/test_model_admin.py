"""The System Intelligence config form: free-text model ids with suggestions, and per-provider validation.

The constants at the top are shared with the other config admin tests.
"""

import json
from unittest.mock import patch

from django.core.cache import cache
from django.forms.models import model_to_dict
from django.test import TestCase

from apps.system_intelligence.admin.config.forms import MODEL_REQUIRED, NOT_IN_BEDROCK, SystemIntelligenceConfigForm
from apps.system_intelligence.admin.config.provider_forms import ModelIdInput
from apps.system_intelligence.models import LLMProviderConfig, SystemIntelligenceConfig

BEDROCK = "apps.system_intelligence.services.bedrock.get_available_models"
USAGE_FIELD = "public_assistant_global_usage"
USAGE_LABEL = "Global Tokens Used (current window)"
GROUPED = [("Anthropic", [("claude-1", "Claude One"), ("claude-2", "Claude Two")])]
MODEL_FIELDS = ("default_model_id", "public_assistant_model_id")


def _form_data(instance, **overrides):
    """POST-style data for *instance* (every field), with *overrides* applied; ``None`` values are dropped."""
    data = model_to_dict(instance)
    data["public_assistant_starter_questions"] = json.dumps(data.get("public_assistant_starter_questions") or [])
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


class ConfigFormSuggestionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.deepseek = LLMProviderConfig.objects.create(name="DeepSeek", preset=LLMProviderConfig.Preset.DEEPSEEK)
        LLMProviderConfig.objects.create(
            name="Gateway", preset=LLMProviderConfig.Preset.CUSTOM, base_url="https://gateway.example.com/v1"
        )

    def test_model_fields_are_free_text_with_bedrock_and_provider_suggestions(self):
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm()
        for field in MODEL_FIELDS:
            widget = form.fields[field].widget
            self.assertIsInstance(widget, ModelIdInput)
            self.assertFalse(form.fields[field].required)
            self.assertEqual(
                widget.suggestions,
                [
                    ("claude-1", "Bedrock · Anthropic · Claude One"),
                    ("claude-2", "Bedrock · Anthropic · Claude Two"),
                    ("deepseek-chat", "DeepSeek · deepseek-chat"),
                    ("deepseek-reasoner", "DeepSeek · deepseek-reasoner"),
                ],
            )

    def test_widget_renders_a_text_input_bound_to_a_datalist(self):
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm(instance=SystemIntelligenceConfig(name="C", default_model_id="m-1"))
        html = str(form["default_model_id"])
        self.assertIn('list="id_default_model_id_suggestions"', html)
        self.assertIn('value="m-1"', html)
        self.assertIn('autocomplete="off"', html)
        self.assertIn('spellcheck="false"', html)
        self.assertIn('<datalist id="id_default_model_id_suggestions">', html)
        self.assertIn('<option value="claude-1">Bedrock · Anthropic · Claude One</option>', html)
        self.assertIn('<option value="deepseek-chat">DeepSeek · deepseek-chat</option>', html)

    def test_widget_without_attrs_derives_the_list_id_and_escapes_suggestions(self):
        widget = ModelIdInput(attrs={"data-role": "model"}, suggestions=[("<m>", "A & B")])
        html = widget.render("model", None)
        self.assertIn('list="id_model_suggestions"', html)
        self.assertIn('data-role="model"', html)
        self.assertIn('<option value="&lt;m&gt;">A &amp; B</option>', html)

    def test_catalog_fetch_failure_keeps_only_provider_suggestions(self):
        with patch(BEDROCK, side_effect=RuntimeError("aws down")):
            form = SystemIntelligenceConfigForm()
        self.assertEqual(
            form.fields["default_model_id"].widget.suggestions,
            [("deepseek-chat", "DeepSeek · deepseek-chat"), ("deepseek-reasoner", "DeepSeek · deepseek-reasoner")],
        )

    def test_duplicate_preset_names_are_suggested_once_per_provider(self):
        names = "apps.system_intelligence.admin.config.forms.suggested_models"
        with patch(BEDROCK, return_value=[]), patch(names, side_effect=lambda preset: ("m", "m")):
            form = SystemIntelligenceConfigForm()
        self.assertEqual(
            form.fields["default_model_id"].widget.suggestions, [("m", "DeepSeek · m"), ("m", "Gateway · m")]
        )

    def test_no_catalog_and_no_providers_suggests_nothing(self):
        LLMProviderConfig.objects.all().delete()
        with patch(BEDROCK, return_value=[]):
            form = SystemIntelligenceConfigForm()
        self.assertEqual(form.fields["public_assistant_model_id"].widget.suggestions, [])
        self.assertIn("<datalist", str(form["public_assistant_model_id"]))


class ConfigFormValidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.provider = LLMProviderConfig.objects.create(name="DeepSeek", preset=LLMProviderConfig.Preset.DEEPSEEK)
        self.config = SystemIntelligenceConfig.objects.create(
            name="Cfg", default_model_id="claude-1", public_assistant_model_id=""
        )

    def _form(self, *, catalog=GROUPED, instance=None, **overrides):
        instance = instance or self.config
        side_effect = catalog if isinstance(catalog, Exception) else None
        with patch(BEDROCK, return_value=catalog, side_effect=side_effect):
            form = SystemIntelligenceConfigForm(data=_form_data(instance, **overrides), instance=instance)
            form.is_valid()
        return form

    def test_known_bedrock_id_is_accepted_and_stripped(self):
        form = self._form(default_model_id="  claude-2  ")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["default_model_id"], "claude-2")

    def test_unknown_bedrock_id_is_rejected_when_catalog_is_readable_and_value_changed(self):
        form = self._form(default_model_id="not-a-bedrock-model")
        self.assertEqual(form.errors["default_model_id"], [NOT_IN_BEDROCK])

    def test_unknown_public_bedrock_id_is_rejected_too(self):
        form = self._form(public_assistant_model_id="kimi-latest")
        self.assertEqual(form.errors["public_assistant_model_id"], [NOT_IN_BEDROCK])

    def test_unchanged_unknown_value_is_accepted(self):
        config = SystemIntelligenceConfig.objects.create(name="Legacy", default_model_id="retired-model")
        form = self._form(instance=config)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["default_model_id"], "retired-model")

    def test_unknown_id_is_accepted_when_catalog_unreadable(self):
        form = self._form(catalog=RuntimeError("aws down"), default_model_id="anything-goes")
        self.assertTrue(form.is_valid(), form.errors)

    def test_unknown_id_is_accepted_when_catalog_is_empty(self):
        form = self._form(catalog=[], default_model_id="anything-goes")
        self.assertTrue(form.is_valid(), form.errors)

    def test_blank_bedrock_model_is_accepted(self):
        form = self._form(default_model_id="   ")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["default_model_id"], "")

    def test_any_model_name_is_accepted_with_a_provider(self):
        form = self._form(
            default_provider=str(self.provider.pk),
            default_model_id="my-fine-tune",
            public_assistant_provider=str(self.provider.pk),
            public_assistant_model_id="kimi-k2-thinking",
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.default_provider, self.provider)
        self.assertEqual(saved.route_for("public"), (self.provider, "kimi-k2-thinking"))

    def test_provider_without_default_model_is_rejected(self):
        form = self._form(default_provider=str(self.provider.pk), default_model_id=" ")
        self.assertEqual(form.errors["default_model_id"], [MODEL_REQUIRED])

    def test_public_provider_without_public_model_is_accepted(self):
        form = self._form(public_assistant_provider=str(self.provider.pk), public_assistant_model_id="")
        self.assertTrue(form.is_valid(), form.errors)
