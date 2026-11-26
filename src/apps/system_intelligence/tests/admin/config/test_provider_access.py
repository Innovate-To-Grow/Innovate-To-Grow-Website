"""Who may route System Intelligence to an AI provider: any Admin.

Every Admin may add, change, key, test and delete providers and choose which provider a config role calls. A signed-in
member who is not an Admin, or an Admin who has been deactivated, is sent to the admin sign-in and changes nothing.
"""

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_member
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
    def _assert_sent_to_sign_in(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def _assert_writes_refused(self, provider):
        """Every provider page, write and key/test action sends the user to sign in; *provider* is unchanged."""
        add = reverse("admin:system_intelligence_llmproviderconfig_add")
        delete = reverse("admin:system_intelligence_llmproviderconfig_delete", args=[provider.pk])
        install, remove, test = (action_url(name, provider) for name in ACTIONS)
        self._assert_sent_to_sign_in(self.client.get(CHANGELIST_URL))
        self._assert_sent_to_sign_in(self.client.get(change_url(provider)))
        self._assert_sent_to_sign_in(self.client.get(add))
        self._assert_sent_to_sign_in(self.client.post(change_url(provider), post_data(provider, name="Hijack")))
        self._assert_sent_to_sign_in(self.client.post(delete, {"post": "yes"}))
        self._assert_sent_to_sign_in(self.client.get(install))
        self._assert_sent_to_sign_in(self.client.post(install, {"api_key": "sk-other-key-9999"}))
        self._assert_sent_to_sign_in(self.client.post(remove, {"confirm": "on"}))
        with patch(RUN_PROBE) as probe:
            self._assert_sent_to_sign_in(self.client.post(test, {"model_id": "deepseek-chat"}))
        probe.assert_not_called()
        provider.refresh_from_db()
        self.assertEqual((provider.name, provider.key_hint, provider.is_enabled), ("DeepSeek", "abcd", True))

    def test_any_admin_may_manage_providers(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        self.client.force_login(make_admin(email="si@example.com"))
        self.assertContains(self.client.get(CHANGELIST_URL), "DeepSeek")
        page = self.client.get(change_url(provider))
        self.assertContains(page, "Installed (ends …abcd)")
        self.assertContains(page, 'name="name"')
        for name in ACTIONS:
            self.assertContains(page, action_url(name, provider))
        self.assertNotContains(page, TEST_KEY)
        self.assertEqual(self.client.get(reverse("admin:system_intelligence_llmproviderconfig_add")).status_code, 200)
        self.assertEqual(self.client.get(action_url("install_key_action", provider)).status_code, 200)
        response = self.client.post(change_url(provider), post_data(provider, name="Renamed"))
        self.assertEqual(response.status_code, 302)
        provider.refresh_from_db()
        self.assertEqual(provider.name, "Renamed")

    def test_a_member_who_is_not_an_admin_is_sent_to_the_sign_in(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        self.client.force_login(make_member(email="member@example.com"))
        self._assert_writes_refused(provider)

    def test_an_inactive_admin_is_sent_to_the_sign_in(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        member = make_admin(email="gone@example.com")
        self.client.force_login(member)
        member.is_active = False
        member.save(update_fields=["is_active"])
        self._assert_writes_refused(provider)


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

    def test_any_admin_can_save_a_provider_model(self):
        page, response = self._open_and_save(default_model_id="my-fine-tune")
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["errors"])
        self.config.refresh_from_db()
        self.assertEqual(self.config.route_for("default"), (self.provider, "my-fine-tune"))

    def test_blank_model_with_a_provider_is_rejected(self):
        _page, response = self._open_and_save(default_model_id="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["adminform"].form.errors["default_model_id"], [MODEL_REQUIRED])

    def test_any_admin_can_change_and_clear_providers(self):
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
    def _form(self, instance, *, without=(), **overrides):
        with patch(BEDROCK, return_value=GROUPED):
            form = SystemIntelligenceConfigForm(data=_form_data(instance, **overrides), instance=instance)
            for name in without:
                del form.fields[name]
            form.is_valid()
        return form

    def test_clearing_the_provider_but_keeping_its_model_is_checked_against_bedrock(self):
        config = SystemIntelligenceConfig.objects.create(
            name="Cfg", default_provider=make_provider(), default_model_id="deepseek-chat"
        )
        form = self._form(config, default_provider=None)
        self.assertEqual(form.errors["default_model_id"], [NOT_IN_BEDROCK])

    def test_a_provider_field_left_off_the_form_keeps_the_saved_provider(self):
        config = SystemIntelligenceConfig.objects.create(
            name="Cfg", default_provider=make_provider(), default_model_id="deepseek-chat"
        )
        form = self._form(config, without=("default_provider",), default_model_id="")
        self.assertEqual(form.errors["default_model_id"], [MODEL_REQUIRED])
