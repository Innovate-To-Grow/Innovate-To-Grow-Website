from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.core.admin.common.base import BaseModelAdmin
from apps.core.admin.confirmation.post_data import is_sensitive_field
from apps.core.admin.service_credentials.microsoft_graph import (
    APPLICATION_FIELDS,
    NO_CERTIFICATE,
    MicrosoftGraphProviderConfigAdmin,
)
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.tests.admin.service_credentials.graph_config.test_microsoft_graph_admin import config_values
from apps.core.tests.graph_helpers import create_graph_config, install_test_certificate
from apps.event.tests.helpers import make_superuser


class MicrosoftGraphProviderConfigAdminTest(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.model_admin = MicrosoftGraphProviderConfigAdmin(MicrosoftGraphProviderConfig, AdminSite())

    def request(self):
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_is_registered_with_the_admin_site(self):
        self.assertIsInstance(admin.site._registry[MicrosoftGraphProviderConfig], MicrosoftGraphProviderConfigAdmin)

    def test_status_badge_for_active_and_inactive_configs(self):
        self.assertEqual(
            self.model_admin.status_badge(MicrosoftGraphProviderConfig(is_active=True)), ("Active", "success")
        )
        self.assertEqual(
            self.model_admin.status_badge(MicrosoftGraphProviderConfig(is_active=False)), ("Inactive", "danger")
        )

    def test_certificate_columns_show_the_current_certificate_or_say_none_is_installed(self):
        config = create_graph_config(**config_values(), certificate=False)
        for method in ("certificate_thumbprint", "certificate_valid_until"):
            with self.subTest(method):
                self.assertEqual(getattr(self.model_admin, method)(config), NO_CERTIFICATE)

        current = install_test_certificate(config)
        install_test_certificate(config, state=MicrosoftGraphCertificate.State.PREVIOUS)

        self.assertEqual(self.model_admin.certificate_thumbprint(config), current.sha1_thumbprint)
        self.assertEqual(self.model_admin.certificate_valid_until(config), current.not_after)

    def test_the_entra_application_is_read_only_while_a_certificate_is_installed(self):
        config = create_graph_config(**config_values(), certificate=False)
        self.assertFalse(set(APPLICATION_FIELDS) & set(self.model_admin.get_readonly_fields(self.request(), config)))

        for state in (MicrosoftGraphCertificate.State.PREVIOUS, MicrosoftGraphCertificate.State.CURRENT):
            install_test_certificate(config, state=state)
            with self.subTest(state):
                readonly = self.model_admin.get_readonly_fields(self.request(), config)
                self.assertTrue(set(APPLICATION_FIELDS) <= set(readonly))
        config.certificates.update(state=MicrosoftGraphCertificate.State.REMOVED)
        self.assertFalse(set(APPLICATION_FIELDS) & set(self.model_admin.get_readonly_fields(self.request(), config)))
        self.assertFalse(set(APPLICATION_FIELDS) & set(self.model_admin.get_readonly_fields(self.request(), None)))

    def test_delete_permission_is_denied_only_for_the_active_config(self):
        active = create_graph_config(**config_values(name="Active", is_active=True))
        inactive = create_graph_config(**config_values(name="Inactive"))

        self.assertFalse(self.model_admin.has_delete_permission(self.request(), active))
        self.assertTrue(self.model_admin.has_delete_permission(self.request(), inactive))
        self.assertTrue(self.model_admin.has_delete_permission(self.request(), None))

    def test_delete_selected_is_not_offered(self):
        # The stock admin offers it to this superuser, so its absence is down to the admin class.
        stock = BaseModelAdmin(MicrosoftGraphProviderConfig, AdminSite())
        self.assertIn("delete_selected", stock.get_actions(self.request()))

        self.assertNotIn("delete_selected", self.model_admin.get_actions(self.request()))

    def test_no_listed_filtered_or_searchable_name_looks_like_a_secret(self):
        for setting in (self.model_admin.list_display, self.model_admin.list_filter, self.model_admin.search_fields):
            for name in setting:
                with self.subTest(name=name):
                    self.assertFalse(is_sensitive_field(name))
