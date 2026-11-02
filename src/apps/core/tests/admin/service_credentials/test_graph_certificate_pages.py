"""The Microsoft Graph certificate pages: who may use them, every accepted input, refusals, rollback, remove, download."""

from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from django.contrib.admin.models import LogEntry
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.admin.service_credentials import microsoft_graph_certificate_forms as forms
from apps.core.admin.service_credentials.microsoft_graph import MicrosoftGraphProviderConfigAdmin
from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphCertificate
from apps.core.services.email.graph.credential import lifecycle, recovery
from apps.core.services.email.graph.credential.loaders import KEY_IN_CERTIFICATE, WRONG_PASSPHRASE
from apps.core.services.email.graph.credential.parsing import KEY_MISMATCH
from apps.core.tests.graph_helpers import create_graph_config, make_certificate
from apps.core.tests.services.graph_credential.helpers import entra_rejection, stored_versions
from apps.event.tests.helpers import make_admin

from .graph_certificate_pages import SENDER, CertificatePagesMixin, key_pem, pem, upload

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

    def test_core_staff_can_open_install_but_cannot_roll_back_or_remove_certificates(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))
        before = list(MicrosoftGraphCertificate.objects.values_list("pk", "state"))
        versions = stored_versions()
        self.script()

        self.assertEqual(self.client.get(self.url("install_certificate")).status_code, 200)
        for name in ("rollback_certificate", "remove_certificates"):
            with self.subTest(name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 403)
                self.assertEqual(self.client.post(self.url(name), self.pem_data(reason="x")).status_code, 403)
        self.assertEqual(self.client.get(self.url("download_certificate")).status_code, 200)
        page = self.client.get(self.change_url)
        self.assertContains(page, 'id="graph-certificate-panel"')
        self.assertContains(page, "Download .cer")
        self.assertContains(page, self.url("install_certificate"))
        for name in ("rollback_certificate", "remove_certificates", "run_access_check"):
            self.assertNotContains(page, self.url(name))
        self.assertEqual(list(MicrosoftGraphCertificate.objects.values_list("pk", "state")), before)
        self.assertEqual(stored_versions(), versions)
        self.assertEqual(self.fake.requests, [])

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


class InstallFormatTests(CertificatePagesMixin, TestCase):
    def assert_installed(self, response, certificate=None):
        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        current = self.config.current_certificate
        expected = (certificate or self.certificate).fingerprint(hashes.SHA1()).hex().upper()
        self.assertEqual(current.sha1_thumbprint, expected)
        self.assertEqual(current.store_version_id, next(iter(stored_versions())))
        self.assertTrue(self.config.credential_configured)
        return current

    def test_pem_certificate_and_key(self):
        response = self.client.post(self.url("install_certificate"), self.pem_data())

        current = self.assert_installed(response)
        page = self.client.get(self.change_url)
        self.assertContains(page, current.sha1_thumbprint)
        self.assertContains(page, "Installed the certificate (SHA-1")

    def test_p12_bundle_and_its_password(self):
        self.assert_installed(self.client.post(self.url("install_certificate"), self.p12_data()))

    def test_encrypted_pem_key_and_its_passphrase(self):
        self.assert_installed(self.client.post(self.url("install_certificate"), self.encrypted_pem_data()))

    def test_der_cer_file_and_key_file(self):
        data = {
            "certificate_file": upload("i2g.cer", self.certificate.public_bytes(serialization.Encoding.DER)),
            "private_key_file": upload("i2g.key", key_pem(self.key)),
        }

        self.assert_installed(self.client.post(self.url("install_certificate"), data))

    def test_expected_thumbprint_is_compared_ignoring_case_colons_and_spaces(self):
        sha1 = self.certificate.fingerprint(hashes.SHA1()).hex()
        typed = " " + ":".join(sha1[i : i + 2] for i in range(0, 40, 2)).replace(":", " ", 3) + " "

        response = self.client.post(self.url("install_certificate"), self.pem_data(expected_sha1=typed))

        self.assert_installed(response)


class InstallRefusalTests(CertificatePagesMixin, TestCase):
    def post(self, data):
        response = self.client.post(self.url("install_certificate"), data)
        self.assertEqual(response.status_code, 200)
        return response

    def assert_nothing_installed(self):
        self.assertFalse(MicrosoftGraphCertificate.objects.exists())
        self.assertEqual(stored_versions(), {})

    def test_a_different_expected_thumbprint_stops_the_install_without_naming_the_real_one(self):
        response = self.post(self.pem_data(expected_sha1="AB" * 20))

        self.assertEqual(response.context["form"].errors["expected_sha1"], [forms.THUMBPRINT_MISMATCH])
        real = self.certificate.fingerprint(hashes.SHA1()).hex().upper()
        self.assertNotContains(response, real)
        self.assert_nothing_installed()

    def test_a_malformed_expected_thumbprint_is_refused(self):
        response = self.post(self.pem_data(expected_sha1="not-hex"))

        self.assertEqual(response.context["form"].errors["expected_sha1"], [forms.THUMBPRINT_FORMAT])
        self.assertContains(response, pem(self.certificate).splitlines()[1])  # the certificate box keeps it
        self.assertNotContains(response, "PRIVATE KEY")
        self.assert_nothing_installed()

    def test_a_key_of_another_certificate_is_refused_on_the_key_input(self):
        _other_certificate, other_key = make_certificate(key_index=1)

        response = self.post(self.pem_data(key=other_key))

        self.assertEqual(response.context["form"].errors["private_key_text"], [KEY_MISMATCH])
        self.assert_nothing_installed()

    def test_a_private_key_in_the_certificate_box_is_refused_and_not_shown_again(self):
        response = self.post({"certificate_text": key_pem(self.key) + pem(self.certificate)})

        self.assertEqual(response.context["form"].errors["certificate_text"], [KEY_IN_CERTIFICATE])
        self.assertNotContains(response, "PRIVATE KEY")
        self.assert_nothing_installed()

    def test_after_an_error_the_certificate_box_shows_only_a_certificate_that_loaded(self):
        _other, other_key = make_certificate(key_index=1)

        response = self.post(self.pem_data(key=other_key))

        self.assertContains(response, pem(self.certificate).splitlines()[1])
        self.assertNotContains(response, "PRIVATE KEY")

    def test_a_wrong_passphrase_is_refused_on_the_password_input(self):
        data = self.encrypted_pem_data() | {"password": "wrong passphrase"}

        response = self.post(data)

        self.assertEqual(response.context["form"].errors["password"], [WRONG_PASSPHRASE])
        self.assert_nothing_installed()

    def test_text_and_file_for_the_same_input_are_refused(self):
        data = self.pem_data(certificate_file=upload("i2g.cer", pem(self.certificate)))

        response = self.post(data)

        self.assertEqual(
            response.context["form"].errors["certificate_file"], [forms.TEXT_AND_FILE.format(what="certificate")]
        )
        self.assert_nothing_installed()

    @override_settings(GRAPH_CERTIFICATE_MAX_INPUT_BYTES=512)
    def test_a_file_over_the_size_limit_is_refused_before_it_is_read(self):
        response = self.post({"bundle": upload("big.p12", b"0" * 513), "password": "x"})

        self.assertEqual(response.context["form"].errors["bundle"], [forms.FILE_TOO_LARGE])
        self.assert_nothing_installed()

    def test_an_active_config_refuses_a_certificate_entra_does_not_trust(self):
        self.script(token=entra_rejection(700027))

        response = self.post(self.pem_data())

        self.assertIn(lifecycle.ACTIVE_NEEDS_TRUST, response.context["form"].non_field_errors()[0])
        self.assert_nothing_installed()

    def test_a_blank_form_asks_for_a_certificate(self):
        response = self.post({})

        self.assertTrue(response.context["form"].errors)
        self.assert_nothing_installed()


class ReissueTests(CertificatePagesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.installed, _key = self.install_existing()

    def test_a_reissued_certificate_with_a_blank_key_keeps_the_installed_key(self):
        reissued, _same_key = make_certificate()  # the shared test key again, in a new certificate
        versions = stored_versions()

        response = self.client.post(self.url("install_certificate"), {"certificate_text": pem(reissued)})

        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        current = self.config.current_certificate
        self.assertNotEqual(current.pk, self.installed.pk)
        self.assertEqual(current.store_version_id, self.installed.store_version_id)
        self.assertEqual(stored_versions(), versions)
        self.assertEqual(self.config.previous_certificate, self.installed)

    def test_a_different_certificate_with_a_blank_key_is_refused(self):
        other, _other_key = make_certificate(key_index=1)

        response = self.client.post(self.url("install_certificate"), {"certificate_text": pem(other)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["private_key_text"], [lifecycle.KEY_REQUIRED])
        self.assertEqual(self.config.current_certificate, self.installed)

    def test_installing_the_current_certificate_again_is_refused(self):
        installed = x509.load_pem_x509_certificate(self.installed.certificate_pem.encode())

        response = self.client.post(self.url("install_certificate"), {"certificate_text": pem(installed)})

        self.assertEqual(response.context["form"].non_field_errors(), [lifecycle.ALREADY_CURRENT])


class RollbackTests(CertificatePagesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.first, _key = self.install_existing()
        self.second, _key = self.install_existing(key_index=1)
        self.script()

    def test_the_confirmation_page_shows_both_certificates(self):
        response = self.client.get(self.url("rollback_certificate"))

        self.assertContains(response, self.first.sha1_thumbprint)
        self.assertContains(response, self.second.sha1_thumbprint)
        self.assertEqual(self.fake.token_requests, [])

    def test_rollback_swaps_the_certificates_after_entra_accepts_the_previous_key(self):
        response = self.client.post(self.url("rollback_certificate"), follow=True)

        self.assertContains(response, "Rolled back to the previous certificate")
        self.assertEqual(self.config.current_certificate, self.first)
        self.assertEqual(self.config.previous_certificate, self.second)

    def test_a_refused_rollback_changes_nothing_and_says_why(self):
        self.script(token=entra_rejection(700027))

        response = self.client.post(self.url("rollback_certificate"), follow=True)

        self.assertContains(response, "The previous certificate was not restored.")
        self.assertEqual(self.config.current_certificate, self.second)

    def test_without_a_previous_certificate_the_page_redirects(self):
        MicrosoftGraphCertificate.objects.filter(pk=self.first.pk).update(state=State.REMOVED)

        response = self.client.get(self.url("rollback_certificate"), follow=True)

        self.assertContains(response, recovery.NO_PREVIOUS)


class RemoveTests(CertificatePagesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.first, _key = self.install_existing()
        self.second, _key = self.install_existing(key_index=1)
        self.email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)

    def remove(self, **data):
        return self.client.post(
            self.url("remove_certificates"), {"confirmation": "REMOVE", "reason": "Key leak"} | data
        )

    def test_the_typed_word_and_a_reason_are_required(self):
        for data, field in (({"confirmation": "remove"}, "confirmation"), ({"reason": ""}, "reason")):
            with self.subTest(field=field):
                response = self.remove(**data)

                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertEqual(self.config.current_certificate, self.second)

    def test_remove_unpins_both_certificates_and_warns_that_email_stops(self):
        response = self.remove()

        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        self.assertIsNone(self.config.current_certificate)
        self.assertIsNone(self.config.previous_certificate)
        page = self.client.get(self.change_url)
        self.assertContains(page, "Removed 2 Microsoft Graph certificate(s).")
        self.assertContains(page, "will fail until a certificate is installed")
        entry = LogEntry.objects.filter(object_id=str(self.config.pk)).latest("action_time")
        self.assertIn("Reason: Key leak", entry.change_message)

    def test_remove_can_switch_email_to_ses_when_ses_is_ready(self):
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="k", secret_access_key="s", default_region="us-west-2"
        )

        self.remove(switch_to_ses="on")

        self.email.refresh_from_db()
        self.assertEqual(self.email.provider, "ses")
        self.assertContains(self.client.get(self.change_url), "Email delivery now uses AWS SES.")

    def test_a_requested_switch_that_ses_cannot_take_is_reported(self):
        self.remove(switch_to_ses="on")

        self.email.refresh_from_db()
        self.assertEqual(self.email.provider, "graph")
        self.assertContains(self.client.get(self.change_url), "SES is not ready")

    def test_with_nothing_installed_the_page_redirects(self):
        self.remove()

        response = self.client.get(self.url("remove_certificates"), follow=True)

        self.assertContains(response, "nothing to remove")


class DownloadTests(CertificatePagesMixin, TestCase):
    def test_the_current_certificate_downloads_as_der(self):
        installed, _key = self.install_existing()

        response = self.client.get(self.url("download_certificate"))

        self.assertEqual(response["Content-Type"], "application/pkix-cert")
        self.assertIn(f"graph-{installed.sha1_thumbprint}.cer", response["Content-Disposition"])
        certificate = x509.load_der_x509_certificate(response.content)
        self.assertEqual(certificate.fingerprint(hashes.SHA1()).hex().upper(), installed.sha1_thumbprint)

    def test_without_a_certificate_the_download_is_a_404(self):
        self.assertEqual(self.client.get(self.url("download_certificate")).status_code, 404)

    def test_an_inactive_standby_config_has_its_own_pages(self):
        standby = create_graph_config(name="Standby", certificate=False)
        self.script(token=entra_rejection(700027))  # not trusted yet: still installed on a standby

        response = self.client.post(self.url("install_certificate", standby), self.pem_data())

        self.assertRedirects(response, self.url("change", standby), fetch_redirect_response=False)
        self.assertEqual(standby.current_certificate.entra_check, "not_trusted")
        self.assertIsNone(self.config.current_certificate)
