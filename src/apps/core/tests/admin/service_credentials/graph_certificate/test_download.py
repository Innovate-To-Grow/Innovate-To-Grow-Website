from cryptography import x509
from cryptography.hazmat.primitives import hashes
from django.test import TestCase

from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.graph_credential.helpers import entra_rejection

from .graph_certificate_pages import CertificatePagesMixin


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
