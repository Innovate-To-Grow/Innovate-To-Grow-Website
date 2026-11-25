import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import IntegrityError, connections
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser
from apps.system_intelligence.admin.config.config_admin import SystemIntelligenceConfigAdmin
from apps.system_intelligence.models import (
    LLMProviderConfig,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.tests.admin.base import rendered_badge
from apps.system_intelligence.tests.admin.config.test_model_admin import BEDROCK, GROUPED, USAGE_FIELD, USAGE_LABEL


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
        self.assertEqual(rendered_badge(self.admin.status_badge, active), ("Active", "success"))
        self.assertEqual(rendered_badge(self.admin.status_badge, inactive), ("Inactive", "danger"))

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

    def test_default_model_display_names_the_provider_without_reading_bedrock(self):
        provider = LLMProviderConfig.objects.create(name="DeepSeek", preset=LLMProviderConfig.Preset.DEEPSEEK)
        obj = SystemIntelligenceConfig(name="A", default_provider=provider, default_model_id="deepseek-chat")
        with patch(BEDROCK) as catalog:
            self.assertEqual(self.admin.default_model_display(obj), "DeepSeek · deepseek-chat")
        catalog.assert_not_called()

    def test_activate_this_config_marks_active_and_redirects(self):
        config = SystemIntelligenceConfig.objects.create(name="ToActivate", is_active=False)
        url = reverse("admin:system_intelligence_systemintelligenceconfig_activate_this_config", args=[config.pk])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin_user)
        self.assertContains(client.get(url), "Activate ToActivate")
        self.assertFalse(SystemIntelligenceConfig.objects.get(pk=config.pk).is_active)
        self.assertEqual(client.post(url).status_code, 403)
        response = client.post(url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        config.refresh_from_db()
        self.assertTrue(config.is_active)
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(config.pk), response.url)

    def test_activation_requires_system_intelligence_access(self):
        config = SystemIntelligenceConfig.objects.create(name="Restricted", is_active=False)
        url = reverse("admin:system_intelligence_systemintelligenceconfig_activate_this_config", args=[config.pk])
        self.client.force_login(make_admin(apps=["cms"]))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        config.refresh_from_db()
        self.assertFalse(config.is_active)

    def test_activation_rejects_other_methods_and_unknown_configs(self):
        config = SystemIntelligenceConfig.objects.create(name="Other", is_active=False)
        url = reverse("admin:system_intelligence_systemintelligenceconfig_activate_this_config", args=[config.pk])
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.get(url.replace(str(config.pk), str(uuid.uuid4()))).status_code, 404)

    def test_activation_race_reports_an_error(self):
        config = SystemIntelligenceConfig.objects.create(name="Racing", is_active=False)
        url = reverse("admin:system_intelligence_systemintelligenceconfig_activate_this_config", args=[config.pk])
        self.client.force_login(self.admin_user)
        with patch.object(SystemIntelligenceConfig, "save", side_effect=IntegrityError("race")):
            response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            [str(m) for m in get_messages(response.wsgi_request)],
            ["Another configuration was activated at the same time. Try again."],
        )

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
        public_fields = list(fieldsets["Public Limits"]["fields"])

        self.assertIn("public_assistant_global_token_limit", public_fields)
        self.assertEqual(
            public_fields.index("public_assistant_global_token_limit"),
            public_fields.index("public_assistant_ip_token_window_seconds") + 1,
        )

    def test_change_form_is_split_into_tabs_that_keep_every_field_once(self):
        names = [str(name) for name, _options in self.admin.fieldsets if name]
        self.assertEqual(names, ["Admin Assistant", "Public Assistant", "Public Limits", "Audit Logging", "Info"])
        self.assertTrue(all(options.get("classes") == ["tab"] for name, options in self.admin.fieldsets if name))
        fields = [field for _name, options in self.admin.fieldsets for field in options["fields"]]
        self.assertEqual(len(fields), len(set(fields)))
        for field in ("default_provider", "system_prompt", "public_assistant_provider", "public_assistant_log_enabled"):
            self.assertIn(field, fields)

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


class ConfigActivationConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_activation_preserves_one_active_configuration(self):
        user = make_superuser()
        configs = [SystemIntelligenceConfig.objects.create(name=name, is_active=False) for name in ("First", "Second")]
        barrier = Barrier(len(configs), timeout=10)

        def activate(config):
            try:
                client = Client()
                client.force_login(user)
                url = reverse(
                    "admin:system_intelligence_systemintelligenceconfig_activate_this_config", args=[config.pk]
                )
                barrier.wait()
                return client.post(url).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(configs)) as workers:
            self.assertEqual(list(workers.map(activate, configs)), [302, 302])
        self.assertEqual(SystemIntelligenceConfig.objects.filter(is_active=True).count(), 1)
