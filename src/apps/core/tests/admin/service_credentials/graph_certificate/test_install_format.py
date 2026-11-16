from cryptography.hazmat.primitives import hashes, serialization
from django.test import TestCase, override_settings

from apps.core.admin.service_credentials import microsoft_graph_certificate_forms as forms
from apps.core.models import MicrosoftGraphCertificate
from apps.core.services.email.graph.credential import lifecycle
from apps.core.services.email.graph.credential.loaders import KEY_IN_CERTIFICATE, WRONG_PASSPHRASE
from apps.core.services.email.graph.credential.parsing import KEY_MISMATCH
from apps.core.tests.graph_helpers import make_certificate
from apps.core.tests.services.graph_credential.helpers import entra_rejection, stored_versions

from .graph_certificate_pages import CertificatePagesMixin, key_pem, pem, upload


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
