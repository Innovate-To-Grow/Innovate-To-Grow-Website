from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.admin.model_admin import (
    SystemIntelligenceActionRequestAdmin,
    SystemIntelligenceConfigAdmin,
    SystemIntelligenceConfigForm,
)
from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import budget

BEDROCK = "apps.core.services.bedrock.get_available_models"
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


class SystemIntelligenceConfigAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = make_superuser()
        self.admin = SystemIntelligenceConfigAdmin(SystemIntelligenceConfig, AdminSite())

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_user
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    def test_status_badge_active_and_inactive(self):
        active = SystemIntelligenceConfig(name="A", is_active=True)
        inactive = SystemIntelligenceConfig(name="B", is_active=False)
        self.assertEqual(self.admin.status_badge(active), ("Active", "success"))
        self.assertEqual(self.admin.status_badge(inactive), ("Inactive", "danger"))

    def test_default_model_display_empty(self):
        obj = SystemIntelligenceConfig(name="A", default_model_id="")
        self.assertEqual(self.admin.default_model_display(obj), "—")

    def test_default_model_display_resolves_friendly_name(self):
        obj = SystemIntelligenceConfig(name="A", default_model_id="claude-2")
        with patch(BEDROCK, return_value=GROUPED):
            self.assertEqual(self.admin.default_model_display(obj), "Claude Two")

    def test_default_model_display_falls_back_to_id_when_not_found(self):
        obj = SystemIntelligenceConfig(name="A", default_model_id="unknown-id")
        with patch(BEDROCK, return_value=GROUPED):
            self.assertEqual(self.admin.default_model_display(obj), "unknown-id")

    def test_default_model_display_falls_back_to_id_on_exception(self):
        obj = SystemIntelligenceConfig(name="A", default_model_id="some-id")
        with patch(BEDROCK, side_effect=RuntimeError("boom")):
            self.assertEqual(self.admin.default_model_display(obj), "some-id")

    def test_activate_this_config_marks_active_and_redirects(self):
        config = SystemIntelligenceConfig.objects.create(name="ToActivate", is_active=False)
        request = self._request()
        response = self.admin.activate_this_config(request, str(config.pk))
        config.refresh_from_db()
        self.assertTrue(config.is_active)
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(config.pk), response.url)
        message_text = [m.message for m in request._messages]
        self.assertTrue(any("active System Intelligence config" in m for m in message_text))

    def test_has_delete_permission_blocks_active_config(self):
        active = SystemIntelligenceConfig.objects.create(name="Active", is_active=True)
        request = self._request()
        self.assertFalse(self.admin.has_delete_permission(request, active))

    def test_has_delete_permission_allows_inactive_config(self):
        inactive = SystemIntelligenceConfig.objects.create(name="Inactive", is_active=False)
        request = self._request()
        self.assertTrue(self.admin.has_delete_permission(request, inactive))

    def test_get_actions_drops_delete_selected(self):
        request = self._request()
        actions = self.admin.get_actions(request)
        self.assertNotIn("delete_selected", actions)

    def test_global_token_limit_sits_with_the_other_assistant_limits(self):
        fieldsets = dict(self.admin.fieldsets)
        public_fields = list(fieldsets["Public Assistant"]["fields"])

        self.assertIn("public_assistant_global_token_limit", public_fields)
        self.assertEqual(
            public_fields.index("public_assistant_global_token_limit"),
            public_fields.index("public_assistant_ip_token_window_seconds") + 1,
        )

    # Save directly: the confirm-on-save step is covered by apps.core's own tests.
    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_change_form_renders_and_saves_the_global_token_limit(self):
        config = SystemIntelligenceConfig.objects.create(name="Editable", is_active=False)
        url = reverse("admin:system_intelligence_systemintelligenceconfig_change", args=[config.pk])
        self.client.force_login(self.admin_user)

        with patch(BEDROCK, return_value=GROUPED):
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'name="public_assistant_global_token_limit"')
            self.assertContains(page, "Global Token Limit (per feature, per 24 hours)")
            # The read-only usage display is on the form, and is not an input.
            self.assertContains(page, USAGE_LABEL)
            self.assertNotContains(page, f'name="{USAGE_FIELD}"')
            self.assertContains(page, "Per-Visitor / Per-Member Token Limit")
            self.assertNotContains(page, "Per-IP")

            data = dict(page.context["adminform"].form.initial)
            data.update(
                {
                    "public_assistant_global_token_limit": "750000",
                    "public_assistant_starter_questions": "[]",
                    "default_model_id": "claude-1",
                    "public_assistant_model_id": "",
                }
            )
            saved = self.client.post(url, {key: value for key, value in data.items() if value is not None})

        self.assertEqual(saved.status_code, 302, getattr(saved, "context", None) and saved.context["errors"])
        config.refresh_from_db()
        self.assertEqual(config.public_assistant_global_token_limit, 750_000)


# The database path is the production path (no Redis): keep it explicit here.
@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class SystemIntelligenceConfigGlobalUsageAdminTests(TestCase):
    """Read-only display of how much of each feature's global budget is used."""

    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.admin = SystemIntelligenceConfigAdmin(SystemIntelligenceConfig, AdminSite())
        self.config = SystemIntelligenceConfig(name="Active", is_active=True)

    def _charge(self, feature, tokens):
        reservation = budget.reserve_budget(
            budget.hash_ip(f"admin-usage-{feature}"),
            estimated_input_tokens=tokens,
            maximum_output_tokens=0,
            limit=0,
            window_seconds=3600,
            global_limit=10**9,
            feature=feature,
        )
        self.assertIsNotNone(reservation)

    def _usage(self, config=None):
        return self.admin.public_assistant_global_usage(config or self.config)

    def test_usage_sits_right_after_the_limit_and_is_read_only(self):
        request = RequestFactory().get("/admin/")
        request.user = self.admin_user
        public_fields = list(dict(self.admin.fieldsets)["Public Assistant"]["fields"])

        self.assertEqual(
            public_fields.index(USAGE_FIELD),
            public_fields.index("public_assistant_global_token_limit") + 1,
        )
        self.assertIn(USAGE_FIELD, self.admin.get_readonly_fields(request, self.config))
        self.assertEqual(self.admin.public_assistant_global_usage.short_description, USAGE_LABEL)

    def test_usage_shows_each_features_tokens_against_the_limit(self):
        self._charge(budget.FEATURE_ASSISTANT, 1_500_000)
        self._charge(budget.FEATURE_AI_SEARCH, 30_000)

        html = self._usage()

        self.assertIsInstance(html, SafeString)
        self.assertIn("<strong>Public assistant:</strong> 1,500,000 of 2,000,000 tokens (75%)", html)
        self.assertIn("<strong>AI search:</strong> 30,000 of 2,000,000 tokens (1%)", html)
        self.assertIn("Each feature has its own counter.", html)
        self.assertNotIn("not active", html)

    def test_usage_shows_when_each_window_ends(self):
        self._charge(budget.FEATURE_ASSISTANT, 100)
        expires_at = PublicAssistantTokenBudget.objects.get(
            pk=budget.GLOBAL_BUDGET_KEYS[budget.FEATURE_ASSISTANT],
        ).window_expires_at

        html = self._usage()

        self.assertIn(f"window ends {timezone.localtime(expires_at):%Y-%m-%d %H:%M %Z}", html)
        self.assertEqual(html.count("window ends "), 1)
        # Nothing has been charged to AI search since its last window ended.
        self.assertIn("<strong>AI search:</strong> 0 of 2,000,000 tokens (0%) &middot; no window open", html)

    def test_usage_before_any_request_is_zero_for_both_features(self):
        html = self._usage()

        self.assertIn("<strong>Public assistant:</strong> 0 of 2,000,000 tokens (0%) &middot; no window open", html)
        self.assertIn("<strong>AI search:</strong> 0 of 2,000,000 tokens (0%) &middot; no window open", html)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_usage_of_an_ended_window_is_not_shown_as_current(self):
        self._charge(budget.FEATURE_ASSISTANT, 900)
        PublicAssistantTokenBudget.objects.update(window_expires_at=timezone.now() - timedelta(seconds=1))

        self.assertIn("<strong>Public assistant:</strong> 0 of 2,000,000 tokens (0%)", self._usage())

    def test_usage_follows_the_limit_of_the_config_being_viewed(self):
        self._charge(budget.FEATURE_ASSISTANT, 1_500_000)
        small = SystemIntelligenceConfig(name="Small", is_active=True, public_assistant_global_token_limit=1_000_000)

        html = self._usage(small)

        # The counter can pass a limit that was lowered after the tokens were spent.
        self.assertIn("1,500,000 of 1,000,000 tokens (150%)", html)

    def test_zero_limit_reads_as_switched_off(self):
        self._charge(budget.FEATURE_AI_SEARCH, 40)
        off = SystemIntelligenceConfig(name="Off", is_active=True, public_assistant_global_token_limit=0)

        html = self._usage(off)

        self.assertIn("<strong>Public assistant:</strong> 0 tokens; switched off (the limit is 0)", html)
        self.assertIn("<strong>AI search:</strong> 40 tokens; switched off (the limit is 0)", html)
        self.assertNotIn("%", html)

    def test_inactive_config_says_its_limit_is_not_the_enforced_one(self):
        inactive = SystemIntelligenceConfig(name="Draft", is_active=False)

        html = self._usage(inactive)

        self.assertIn("This config is not active", html)
        self.assertIn("the active config&#x27;s limit is the one enforced", html)

    def test_unreadable_budget_store_never_breaks_the_form(self):
        with (
            patch(
                "apps.system_intelligence.admin.model_admin.global_budget_usage",
                side_effect=budget.BudgetBackendUnavailable("store down"),
            ),
            self.assertLogs("apps.system_intelligence.admin.model_admin", level="ERROR") as logs,
        ):
            text = self._usage()

        self.assertEqual(text, "Usage is unavailable right now (the budget store could not be read).")
        self.assertIn("Could not read the assistant global token budget usage", logs.output[0])

    @override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
    def test_usage_without_a_known_window_end_still_reports_the_tokens(self):
        # The cache-backed (development) budget does not expose the window end.
        self._charge(budget.FEATURE_ASSISTANT, 500)

        html = self._usage()

        self.assertIn("<strong>Public assistant:</strong> 500 of 2,000,000 tokens (0%) &middot; window open", html)
        self.assertIn("<strong>AI search:</strong> 0 of 2,000,000 tokens (0%) &middot; no window open", html)

    def test_change_and_add_forms_render_the_usage(self):
        saved = SystemIntelligenceConfig.objects.create(name="Saved", is_active=True)
        self._charge(budget.FEATURE_ASSISTANT, 1_234)
        self.client.force_login(self.admin_user)

        with patch(BEDROCK, return_value=GROUPED):
            change = self.client.get(
                reverse("admin:system_intelligence_systemintelligenceconfig_change", args=[saved.pk]),
            )
            add = self.client.get(reverse("admin:system_intelligence_systemintelligenceconfig_add"))

        for page in (change, add):
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, USAGE_LABEL)
            self.assertContains(page, "<strong>Public assistant:</strong> 1,234 of 2,000,000 tokens (0%)")
            self.assertContains(page, "<strong>AI search:</strong> 0 of 2,000,000 tokens (0%)")
            self.assertNotContains(page, f'name="{USAGE_FIELD}"')
        self.assertNotContains(change, "This config is not active")


class SystemIntelligenceActionRequestAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = make_superuser()
        self.admin = SystemIntelligenceActionRequestAdmin(SystemIntelligenceActionRequest, AdminSite())

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_user
        return request

    def test_no_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(self._request()))

    def test_no_delete_permission(self):
        self.assertFalse(self.admin.has_delete_permission(self._request()))
