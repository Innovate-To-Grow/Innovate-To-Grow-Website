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

    def test_public_input_limits_have_bounded_defaults(self):
        config = SystemIntelligenceConfig()
        self.assertEqual(config.public_assistant_max_history_chars, 8000)
        self.assertEqual(config.public_assistant_max_context_chars, 24000)
        self.assertEqual(config.public_assistant_max_estimated_input_tokens, 12000)


class TokenLimitFieldTests(TestCase):
    def _field(self, name):
        return SystemIntelligenceConfig._meta.get_field(name)

    def test_global_limit_defaults_to_two_million_tokens(self):
        self.assertEqual(SystemIntelligenceConfig().public_assistant_global_token_limit, 2_000_000)
        saved = SystemIntelligenceConfig.objects.create(name="Saved")
        saved.refresh_from_db()
        self.assertEqual(saved.public_assistant_global_token_limit, 2_000_000)

    def test_global_limit_has_a_database_default(self):
        # Backend tasks still running the previous release insert rows without
        # this column during a rolling deploy; the database must fill it in.
        field = self._field("public_assistant_global_token_limit")
        self.assertTrue(field.has_db_default())
        self.assertEqual(field.db_default, 2_000_000)

    def test_global_limit_help_text_explains_scope_sizing_cost_and_zero(self):
        field = self._field("public_assistant_global_token_limit")
        self.assertEqual(str(field.verbose_name), "Global Token Limit (per feature, per 24 hours)")
        for expected in (
            "Spend ceiling",
            # A per-feature ceiling per window, not one shared pot.
            "applied to EACH feature separately",
            "each have their own counter",
            "AI search",
            "24-hour window",
            "the other feature keeps working",
            "Size it",
            # Worst case: every token billed at the OUTPUT price, per feature.
            "Worst-case daily cost is about this value x the model's OUTPUT price per token, for each feature",
            "0 switches off the model calls of both features",
        ):
            self.assertIn(expected, field.help_text)
        for stale in ("TOGETHER", "mostly input tokens"):
            self.assertNotIn(stale, field.help_text)

    def test_per_actor_fields_are_relabelled_but_keep_their_columns(self):
        limit = self._field("public_assistant_ip_token_limit")
        window = self._field("public_assistant_ip_token_window_seconds")

        # Same database columns (no rename migration) ...
        self.assertEqual(limit.column, "public_assistant_ip_token_limit")
        self.assertEqual(window.column, "public_assistant_ip_token_window_seconds")
        # ... but nothing tells an admin these are per-IP limits any more.
        for field in (limit, window):
            self.assertIn("Per-Visitor / Per-Member", str(field.verbose_name))
            self.assertNotIn("Per-IP", str(field.verbose_name))
            self.assertNotIn("per-IP", field.help_text)
        self.assertIn("Not keyed on IP address", limit.help_text)
        self.assertIn("0 disables this per-visitor/member limit", limit.help_text)
        # Callers without a visitor identity are not held to it.
        self.assertIn("share one bucket that is exempt from this limit", limit.help_text)
        self.assertNotIn("single bucket of this size", limit.help_text)
