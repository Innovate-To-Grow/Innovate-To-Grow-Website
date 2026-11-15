from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.admin.service_credentials.microsoft_graph import (
    GRAPH_FORM_FIELDS,
    NO_CERTIFICATE,
)
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.tests.admin.service_credentials.graph_config.test_microsoft_graph_admin import (
    CLIENT_ID,
    MAILBOX,
    OTHER_CLIENT_ID,
    config_values,
    form_data,
)
from apps.core.tests.graph_helpers import create_graph_config, install_test_certificate, private_key_lines
from apps.event.tests.helpers import make_admin, make_superuser


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MicrosoftGraphProviderConfigAdminPagesTest(TestCase):
    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = create_graph_config(**config_values(is_active=True))
        self.certificate = self.config.current_certificate
        self.changelist_url = reverse("admin:core_microsoftgraphproviderconfig_changelist")
        self.add_url = reverse("admin:core_microsoftgraphproviderconfig_add")
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])
        self.delete_url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[self.config.pk])

    def post_data(self, **overrides):
        return form_data(is_active="on", _save="Save") | overrides

    def assert_no_key_material(self, response):
        self.assertNotContains(response, "PRIVATE KEY")
        for line in private_key_lines():
            self.assertNotContains(response, line)

    def test_changelist_lists_configs_with_their_thumbprint_and_no_bulk_delete(self):
        create_graph_config(**config_values(name="Standby", mailbox="standby@example.com"), certificate=False)

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MAILBOX)
        self.assertContains(response, "standby@example.com")
        self.assertContains(response, self.certificate.sha1_thumbprint)
        self.assertContains(response, NO_CERTIFICATE)
        self.assertNotContains(response, "delete_selected")
        self.assert_no_key_material(response)

    def test_add_page_renders_no_credential_input(self):
        response = self.client.get(self.add_url)

        self.assertEqual(response.status_code, 200)
        for name in GRAPH_FORM_FIELDS:
            self.assertContains(response, f'name="{name}"')
        for name in ("client_secret", "private_key", "certificate", "auth_method"):
            self.assertNotContains(response, f'name="{name}"')
        self.assertNotContains(response, 'type="password"')

    def test_change_page_shows_the_certificate_panel_and_never_key_material(self):
        previous = install_test_certificate(self.config, state=MicrosoftGraphCertificate.State.PREVIOUS)

        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        for value in (
            self.certificate.sha1_thumbprint,
            self.certificate.sha256_fingerprint,
            self.certificate.serial_number,
            self.certificate.subject,
            # In the site's time zone, as the admin shows every date, with the zone named.
            f"{timezone.localtime(self.certificate.not_after):%Y-%m-%d %H:%M %Z}",
            f'Stored in the in-memory store (tests only), version <span class="break-all font-mono">'
            f"{self.certificate.store_version_id}",
            "Thumbprint (SHA-1, as shown in Entra)",
            "Expires in ",
            "Previous certificate (kept for rollback)",
            previous.sha1_thumbprint,
        ):
            self.assertContains(response, value)
        self.assertNotContains(response, 'name="tenant_id"')
        self.assertNotContains(response, 'name="client_id"')
        self.assert_no_key_material(response)

    def test_without_a_certificate_the_panel_says_so_and_the_application_is_editable(self):
        standby = create_graph_config(**config_values(name="Standby"), certificate=False)

        response = self.client.get(reverse("admin:core_microsoftgraphproviderconfig_change", args=[standby.pk]))

        self.assertContains(response, "None installed: Microsoft Graph cannot send or read mail")
        self.assertContains(response, 'name="tenant_id"')
        self.assertContains(response, 'name="client_id"')

    def test_valid_change_is_saved_and_keeps_the_certificate(self):
        response = self.client.post(self.change_url, self.post_data(name="Renamed"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Renamed")
        self.assertEqual(self.config.current_certificate, self.certificate)
        self.assertTrue(self.config.is_active)
        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        self.assertNotIn("PRIVATE", entry.get_change_message())

    def test_a_posted_application_change_under_the_certificate_is_ignored(self):
        response = self.client.post(self.change_url, self.post_data(client_id=OTHER_CLIENT_ID, name="Renamed"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual((self.config.name, self.config.client_id), ("Renamed", CLIENT_ID))

    def test_add_creates_an_inactive_config_without_a_certificate(self):
        response = self.client.post(self.add_url, form_data(name="Standby", _save="Save"))

        self.assertEqual(response.status_code, 302)
        created = MicrosoftGraphProviderConfig.objects.get(name="Standby")
        self.assertFalse(created.is_active)
        self.assertIsNone(created.current_certificate)
        self.config.refresh_from_db()
        self.assertTrue(self.config.is_active)

    def test_activating_a_standby_through_the_admin_deactivates_the_active_config(self):
        standby = create_graph_config(**config_values(name="Standby"))
        url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[standby.pk])

        response = self.client.post(url, self.post_data(name="Standby"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        standby.refresh_from_db()
        self.assertFalse(self.config.is_active)
        self.assertTrue(standby.is_active)

    def test_active_config_cannot_be_deleted(self):
        self.assertEqual(self.client.get(self.delete_url).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url, {"post": "yes"}).status_code, 403)

        self.assertTrue(MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).exists())

    def test_inactive_config_can_be_deleted_with_its_certificate_rows(self):
        standby = create_graph_config(**config_values(name="Standby"))
        url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[standby.pk])

        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.filter(pk=standby.pk).exists())
        self.assertFalse(MicrosoftGraphCertificate.objects.filter(config_id=standby.pk).exists())

    def test_only_staff_granted_the_core_app_can_reach_the_config(self):
        urls = (self.changelist_url, self.add_url, self.change_url)

        self.client.force_login(make_admin(apps=["cms"], email="cms-editor@example.com"))
        for url in urls:
            with self.subTest(grant="cms", url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(self.change_url, self.post_data(mailbox="attacker@example.com"))
        self.assertEqual(response.status_code, 403)
        self.config.refresh_from_db()
        self.assertEqual(self.config.mailbox, MAILBOX)

        self.client.force_login(make_admin(apps=["core"], email="core-admin@example.com"))
        for url in urls:
            with self.subTest(grant="core", url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
