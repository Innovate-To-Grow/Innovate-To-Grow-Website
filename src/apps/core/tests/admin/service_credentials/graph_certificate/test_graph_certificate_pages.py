"""The Microsoft Graph certificate pages: who may use them, every accepted input, refusals, rollback, remove, download."""

from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from django.contrib.admin.models import LogEntry
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.admin.service_credentials.microsoft_graph import MicrosoftGraphProviderConfigAdmin
from apps.core.models import EmailServiceConfig, MicrosoftGraphCertificate
from apps.core.tests.graph_helpers import create_graph_config, make_certificate
from apps.core.tests.services.graph_credential.helpers import stored_versions
from apps.event.tests.helpers import make_admin

from .graph_certificate_pages import SENDER, CertificatePagesMixin

State = MicrosoftGraphCertificate.State
ACTIONS = ("install_certificate", "rollback_certificate", "remove_certificates")


class AccessTests(CertificatePagesMixin, TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        self.current, _key = self.install_existing()
        self.install_existing(key_index=1)  # the first one becomes previous, so every action applies

    def test_superuser_can_open_every_certificate_page(self):
        for name in (*ACTIONS, "download_certificate"):
            with self.subTest(name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 200)

    def test_core_staff_can_open_every_certificate_page_like_a_superuser(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))

        for name in (*ACTIONS, "download_certificate"):
            with self.subTest(name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 200)
        page = self.client.get(self.change_url)
        self.assertContains(page, 'id="graph-certificate-panel"')
        for label in ("Install certificate", "Roll back to previous", "Download .cer", "Remove (emergency)"):
            self.assertContains(page, label)
        for name in (*ACTIONS, "run_access_check"):
            self.assertContains(page, self.url(name))

    def test_mail_only_and_other_staff_cannot_reach_any_certificate_page(self):
        before = list(MicrosoftGraphCertificate.objects.values_list("pk", "state"))
        versions = stored_versions()
        self.script()
        for apps in (["mail"], ["cms"], []):
            self.client.force_login(make_admin(apps=apps, email=f"staff-{'-'.join(apps) or 'none'}@example.com"))
            for name in (*ACTIONS, "download_certificate"):
                with self.subTest(apps=apps, name=name):
                    self.assertEqual(self.client.get(self.url(name)).status_code, 403)
                    self.assertEqual(self.client.post(self.url(name), self.pem_data()).status_code, 403)
        self.assertEqual(list(MicrosoftGraphCertificate.objects.values_list("pk", "state")), before)
        self.assertEqual(stored_versions(), versions)
        self.assertEqual(self.fake.requests, [])

    def test_install_respects_change_permission_for_the_selected_config(self):
        self.client.force_login(make_admin(apps=["core"], email="core-denied@example.com"))
        before = list(MicrosoftGraphCertificate.objects.values_list("pk", "state"))
        versions = stored_versions()
        self.script()

        with patch.object(
            MicrosoftGraphProviderConfigAdmin, "has_change_permission", autospec=True, return_value=False
        ) as allowed:
            self.assertEqual(self.client.get(self.url("install_certificate")).status_code, 403)
            self.assertEqual(self.client.post(self.url("install_certificate"), self.pem_data()).status_code, 403)

        self.assertEqual(allowed.call_count, 2)
        for call in allowed.call_args_list:
            self.assertEqual(call.args[-1], self.config)
        self.assertEqual(list(MicrosoftGraphCertificate.objects.values_list("pk", "state")), before)
        self.assertEqual(stored_versions(), versions)
        self.assertEqual(self.fake.requests, [])

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        self.client.logout()
        for name in (*ACTIONS, "download_certificate"):
            with self.subTest(name):
                response = self.client.get(self.url(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_superuser_sees_every_action_on_the_change_page(self):
        page = self.client.get(self.change_url)

        for name in (*ACTIONS, "download_certificate"):
            self.assertContains(page, self.url(name))

    def test_an_unknown_config_is_a_404(self):
        url = self.url("install_certificate").replace(str(self.config.pk), "00000000-0000-0000-0000-000000000000")

        self.assertEqual(self.client.get(url).status_code, 404)


class CoreStaffInstallTests(CertificatePagesMixin, TestCase):
    client_class = APIClient

    def test_core_staff_install_and_replace_a_standby_certificate_without_activating_or_sending(self):
        actor = make_admin(apps=["core"], email="core-install@example.com")
        self.client.force_login(actor)
        standby = create_graph_config(name="Standby", is_active=False, certificate=False, scope=(SENDER,))
        email_settings = list(EmailServiceConfig.objects.values())

        response = self.client.post(self.url("install_certificate", standby), self.pem_data())

        self.assertRedirects(response, self.url("change", standby), fetch_redirect_response=False)
        first = standby.current_certificate
        self.assertEqual(first.sha1_thumbprint, self.certificate.fingerprint(hashes.SHA1()).hex().upper())
        self.assertIn(first.store_version_id, stored_versions())
        entry = LogEntry.objects.get(object_id=str(standby.pk))
        self.assertEqual(entry.user_id, actor.pk)
        self.assertIn(first.sha1_thumbprint, entry.change_message)
        self.assertEqual(len(self.fake.token_requests), 1)
        self.assertEqual(self.fake.send_requests, [])

        certificate, key = make_certificate(key_index=1)
        self.script()
        response = self.client.post(
            self.url("install_certificate", standby), self.pem_data(certificate=certificate, key=key)
        )

        self.assertRedirects(response, self.url("change", standby), fetch_redirect_response=False)
        current = standby.current_certificate
        self.assertEqual(current.sha1_thumbprint, certificate.fingerprint(hashes.SHA1()).hex().upper())
        self.assertEqual(standby.previous_certificate, first)
        self.assertEqual(set(stored_versions()), {first.store_version_id, current.store_version_id})
        entry = LogEntry.objects.filter(object_id=str(standby.pk)).latest("action_time")
        self.assertEqual(entry.user_id, actor.pk)
        self.assertIn(current.sha1_thumbprint, entry.change_message)
        standby.refresh_from_db()
        self.config.refresh_from_db()
        self.assertFalse(standby.is_active)
        self.assertTrue(self.config.is_active)
        self.assertEqual(list(EmailServiceConfig.objects.values()), email_settings)
        self.assertEqual(len(self.fake.token_requests), 1)
        self.assertEqual(self.fake.send_requests, [])
