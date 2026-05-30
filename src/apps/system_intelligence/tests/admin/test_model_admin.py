from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.admin.model_admin import (
    SystemIntelligenceActionRequestAdmin,
    SystemIntelligenceConfigAdmin,
    SystemIntelligenceConfigForm,
)
from apps.system_intelligence.models import SystemIntelligenceActionRequest, SystemIntelligenceConfig

BEDROCK = "apps.core.services.bedrock.get_available_models"
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
