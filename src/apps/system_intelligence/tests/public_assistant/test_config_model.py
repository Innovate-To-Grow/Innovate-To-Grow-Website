"""Tests for the public-assistant fields/resolver on SystemIntelligenceConfig."""

from django.test import TestCase

from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.models.config import default_starter_questions


class PublicModelIdTests(TestCase):
    def test_public_model_id_prefers_explicit(self):
        config = SystemIntelligenceConfig(public_assistant_model_id="explicit-model", default_model_id="fallback-model")
        self.assertEqual(config.public_model_id, "explicit-model")

    def test_public_model_id_falls_back_to_default(self):
        config = SystemIntelligenceConfig(public_assistant_model_id="", default_model_id="fallback-model")
        self.assertEqual(config.public_model_id, "fallback-model")

    def test_default_starter_questions_is_non_empty_list(self):
        questions = default_starter_questions()
        self.assertIsInstance(questions, list)
        self.assertTrue(questions)
        self.assertTrue(all(isinstance(q, str) for q in questions))
