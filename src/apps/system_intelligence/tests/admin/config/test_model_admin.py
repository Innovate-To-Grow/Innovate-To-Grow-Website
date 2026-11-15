from unittest.mock import patch

from django.test import TestCase

from apps.system_intelligence.admin.config.forms import SystemIntelligenceConfigForm
from apps.system_intelligence.models import (
    SystemIntelligenceConfig,
)

BEDROCK = "apps.system_intelligence.services.bedrock.get_available_models"
USAGE_FIELD = "public_assistant_global_usage"
USAGE_LABEL = "Global Tokens Used (current window)"
GROUPED = [("Anthropic", [("claude-1", "Claude One"), ("claude-2", "Claude Two")])]


class SystemIntelligenceConfigFormTests(TestCase):
    def test_choices_built_from_available_models(self):
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm()
        choices = form.fields["default_model_id"].choices
        self.assertEqual(choices[0], ("", "---------"))
        self.assertEqual(choices[1], ("Anthropic", [("claude-1", "Claude One"), ("claude-2", "Claude Two")]))

    def test_configured_model_not_in_catalog_is_appended(self):
        instance = SystemIntelligenceConfig(name="C", default_model_id="custom-model-id")
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm(instance=instance)
        choices = form.fields["default_model_id"].choices
        self.assertIn(("Configured Model", [("custom-model-id", "custom-model-id")]), choices)

    def test_fetch_failure_falls_back_to_current_model_only(self):
        instance = SystemIntelligenceConfig(name="C", default_model_id="fallback-model")
        with patch(BEDROCK, side_effect=RuntimeError("aws down")):
            form = SystemIntelligenceConfigForm(instance=instance)
        self.assertEqual(
            form.fields["default_model_id"].choices,
            [("", "---------"), ("fallback-model", "fallback-model")],
        )

    def test_fetch_failure_without_current_model_uses_blank_choice(self):
        instance = SystemIntelligenceConfig(name="C", default_model_id="")
        with patch(BEDROCK, side_effect=RuntimeError("aws down")):
            form = SystemIntelligenceConfigForm(instance=instance)
        self.assertEqual(form.fields["default_model_id"].choices, [("", "---------")])

    def test_public_assistant_model_choices_built_from_available_models(self):
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm()
        choices = form.fields["public_assistant_model_id"].choices
        self.assertEqual(choices[0], ("", "Use Default AI Model"))
        self.assertEqual(choices[1], ("Anthropic", [("claude-1", "Claude One"), ("claude-2", "Claude Two")]))

    def test_public_assistant_configured_model_not_in_catalog_is_appended(self):
        instance = SystemIntelligenceConfig(name="C", public_assistant_model_id="custom-public-id")
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm(instance=instance)
        choices = form.fields["public_assistant_model_id"].choices
        self.assertIn(("Configured Model", [("custom-public-id", "custom-public-id")]), choices)

    def test_public_assistant_fetch_failure_falls_back_to_current_model_only(self):
        instance = SystemIntelligenceConfig(name="C", public_assistant_model_id="fallback-public")
        with patch(BEDROCK, side_effect=RuntimeError("aws down")):
            form = SystemIntelligenceConfigForm(instance=instance)
        self.assertEqual(
            form.fields["public_assistant_model_id"].choices,
            [("", "Use Default AI Model"), ("fallback-public", "fallback-public")],
        )

    def test_public_assistant_fetch_failure_without_current_model_uses_blank_choice(self):
        instance = SystemIntelligenceConfig(name="C", public_assistant_model_id="")
        with patch(BEDROCK, side_effect=RuntimeError("aws down")):
            form = SystemIntelligenceConfigForm(instance=instance)
        self.assertEqual(form.fields["public_assistant_model_id"].choices, [("", "Use Default AI Model")])
