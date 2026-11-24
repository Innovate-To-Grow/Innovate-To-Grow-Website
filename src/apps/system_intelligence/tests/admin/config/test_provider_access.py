"""Who may route System Intelligence to an AI provider: only the I2G Master (superuser).

Non-superuser System Intelligence staff may view providers but not add, change, key, test or delete them, and see the
config's provider fields read-only (the form then validates model names against the saved provider).
"""

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_admin
from apps.system_intelligence.admin.config.forms import MODEL_REQUIRED, NOT_IN_BEDROCK, SystemIntelligenceConfigForm
from apps.system_intelligence.models import SystemIntelligenceConfig

from .test_model_admin import BEDROCK, GROUPED, _form_data
from .test_provider_admin import (
    CHANGELIST_URL,
    RUN_PROBE,
    TEST_KEY,
    ProviderAdminTestCase,
    action_url,
    change_url,
    make_provider,
    post_data,
)

ACTIONS = ("install_key_action", "remove_key_action", "test_connection_action")


# Typed confirmation off: the delete POST then reaches Django's own permission check instead of the confirm step.
@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ProviderAdminAccessTests(ProviderAdminTestCase):
    def _assert_writes_refused(self, provider):
        """Add, change, delete and every key/test action answer 403, and *provider* is unchanged."""
        add = reverse("admin:system_intelligence_llmproviderconfig_add")
        delete = reverse("admin:system_intelligence_llmproviderconfig_delete", args=[provider.pk])
        install, remove, test = (action_url(name, provider) for name in ACTIONS)
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(change_url(provider), post_data(provider, name="Hijack")).status_code, 403)
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(self.client.get(install).status_code, 403)
        self.assertEqual(self.client.post(install, {"api_key": "sk-other-key-9999"}).status_code, 403)
        self.assertEqual(self.client.post(remove, {"confirm": "on"}).status_code, 403)
        with patch(RUN_PROBE) as probe:
            self.assertEqual(self.client.post(test, {"model_id": "deepseek-chat"}).status_code, 403)
        probe.assert_not_called()
        provider.refresh_from_db()
        self.assertEqual((provider.name, provider.key_hint, provider.is_enabled), ("DeepSeek", "abcd", True))

    def test_system_intelligence_staff_can_only_view(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        self.client.force_login(make_admin(apps=["system_intelligence"], email="si@example.com"))
        self.assertContains(self.client.get(CHANGELIST_URL), "DeepSeek")
        page = self.client.get(change_url(provider))
        self.assertContains(page, "Installed (ends …abcd)")
        self.assertNotContains(page, 'name="name"')
        for name in ACTIONS:
            self.assertNotContains(page, action_url(name, provider))
        self.assertNotContains(page, TEST_KEY)
        self._assert_writes_refused(provider)

    def test_other_app_staff_is_forbidden_everywhere(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        self.client.force_login(make_admin(apps=["cms"], email="cms@example.com"))
        self.assertEqual(self.client.get(CHANGELIST_URL).status_code, 403)
        self.assertEqual(self.client.get(change_url(provider)).status_code, 403)
        self._assert_writes_refused(provider)

    def test_superuser_change_page_offers_every_action(self):
        page = self.client.get(change_url(provider := make_provider(key=TEST_KEY)))
        for name in ACTIONS:
            self.assertContains(page, action_url(name, provider))


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ConfigProviderFieldAccessTests(ProviderAdminTestCase):
    def setUp(self):
        super().setUp()
        self.provider = make_provider()
        self.config = SystemIntelligenceConfig.objects.create(
            name="Routed", default_provider=self.provider, default_model_id="deepseek-chat"
        )
        self.url = reverse("admin:system_intelligence_systemintelligenceconfig_change", args=[self.config.pk])

    def _open_and_save(self, **changes):
        """GET the change page, then POST its own initial data with *changes*; returns ``(page, response)``."""
        with patch(BEDROCK, return_value=GROUPED):
            page = self.client.get(self.url)
            self.assertEqual(page.status_code, 200)
            data = {**page.context["adminform"].form.initial, "public_assistant_starter_questions": "[]", **changes}
            response = self.client.post(self.url, {key: value for key, value in data.items() if value is not None})
        return page, response

    def _login_staff(self):
        self.client.force_login(make_admin(apps=["system_intelligence"], email="si@example.com"))

    def test_staff_see_the_providers_read_only_and_can_save_a_provider_model(self):
        self._login_staff()
        page, response = self._open_and_save(default_model_id="my-fine-tune")
        self.assertNotContains(page, 'name="default_provider"')
        self.assertNotContains(page, 'name="public_assistant_provider"')
        self.assertContains(page, "DeepSeek (disabled)")
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["errors"])
        self.config.refresh_from_db()
        self.assertEqual(self.config.route_for("default"), (self.provider, "my-fine-tune"))

    def test_staff_post_cannot_change_the_provider(self):
        self._login_staff()
        _page, response = self._open_and_save(default_provider="", default_model_id="claude-1")
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.route_for("default"), (self.provider, "claude-1"))

    def test_staff_blank_model_with_the_saved_provider_is_rejected(self):
        self._login_staff()
        _page, response = self._open_and_save(default_model_id="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["adminform"].form.errors["default_model_id"], [MODEL_REQUIRED])

    def test_superuser_can_change_and_clear_providers(self):
        page, response = self._open_and_save(
            public_assistant_provider=str(self.provider.pk), public_assistant_model_id="deepseek-reasoner"
        )
        self.assertContains(page, 'name="default_provider"')
        self.assertContains(page, 'name="public_assistant_provider"')
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.route_for("public"), (self.provider, "deepseek-reasoner"))

        _page, response = self._open_and_save(default_provider="", default_model_id="claude-2")
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.route_for("default"), (None, "claude-2"))


class ConfigFormProviderChangeTests(ProviderAdminTestCase):
    def _form(self, instance, **overrides):
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm(data=_form_data(instance, **overrides), instance=instance)
            form.is_valid()
        return form

    def test_clearing_the_provider_but_keeping_its_model_is_checked_against_bedrock(self):
        config = SystemIntelligenceConfig.objects.create(
            name="Cfg", default_provider=make_provider(), default_model_id="deepseek-chat"
        )
        form = self._form(config, default_provider=None)
        self.assertEqual(form.errors["default_model_id"], [NOT_IN_BEDROCK])
