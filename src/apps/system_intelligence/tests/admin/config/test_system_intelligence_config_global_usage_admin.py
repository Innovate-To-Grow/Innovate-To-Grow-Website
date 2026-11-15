from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.admin.config.config_admin import SystemIntelligenceConfigAdmin
from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.admin.config.test_model_admin import BEDROCK, GROUPED, USAGE_FIELD, USAGE_LABEL


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
                "apps.system_intelligence.admin.config.config_admin.global_budget_usage",
                side_effect=budget.BudgetBackendUnavailable("store down"),
            ),
            self.assertLogs("apps.system_intelligence.admin.config.config_admin", level="ERROR") as logs,
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
