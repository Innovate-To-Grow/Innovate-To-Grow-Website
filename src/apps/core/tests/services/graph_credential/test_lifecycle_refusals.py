from unittest.mock import patch

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.credential_store import CredentialStoreError
from apps.core.services.email.graph.credential import entra_check, lifecycle, stored_key
from apps.core.services.email.graph.credential.lifecycle import CertificateChangeError
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID
from apps.core.tests.services.graph_credential.helpers import (
    entra_rejection,
    parsed_certificate,
    stored_versions,
)
from apps.core.tests.services.graph_credential.test_lifecycle import _InstallCase


class InstallTests(_InstallCase):
    def test_wrong_tenant_app_or_disabled_app_refuses_before_anything_is_stored(self):
        cases = {
            700016: ("unauthorized_client", "no application with this client ID"),
            90002: ("invalid_request", "does not know this tenant"),
            7000112: ("unauthorized_client", "application is disabled"),
            7000215: ("invalid_client", "rejected this certificate"),
        }
        for number, (error, message) in cases.items():
            with self.subTest(number):
                self.script(token=entra_rejection(number, error))

                with self.assertRaisesMessage(CertificateChangeError, message) as caught:
                    self.install(parsed_certificate()[0])

                self.assertIn(f"AADSTS{number}", str(caught.exception))
                self.assertIn("Nothing was changed", str(caught.exception))
                self.assertEqual(stored_versions(), {})
                self.assertFalse(MicrosoftGraphCertificate.objects.exists())

    def test_a_certificate_entra_does_not_trust_yet_is_installed_on_a_config_that_is_not_sending(self):
        self.script(token=entra_rejection(700027))

        certificate = self.install(parsed_certificate()[0])

        self.assertEqual(certificate.entra_check, entra_check.NOT_TRUSTED)
        self.assertEqual(certificate.entra_check_code, "invalid_client AADSTS700027")

    def test_an_unreachable_entra_still_installs_on_a_config_that_is_not_sending(self):
        self.script(token=ConnectFailed())

        self.assertEqual(self.install(parsed_certificate()[0]).entra_check, entra_check.UNREACHABLE)

    def test_the_sending_config_only_accepts_a_certificate_entra_accepts(self):
        self.config.is_active = True
        self.config.save()
        for label, answer in {
            "not trusted": entra_rejection(700027),
            "unreachable": HttpResponse(503, {}, b""),
        }.items():
            with self.subTest(label):
                self.script(token=answer)

                with self.assertRaisesMessage(CertificateChangeError, lifecycle.ACTIVE_NEEDS_TRUST):
                    self.install(parsed_certificate()[0])

                self.assertEqual(stored_versions(), {})
                self.assertIsNone(self.config.current_certificate)

    def test_a_store_failure_stores_and_pins_nothing(self):
        failure = CredentialStoreError("The credential could not be saved.", code="AccessDeniedException")
        with patch.object(stored_key, "get_store") as get_store_mock:
            get_store_mock.return_value.put.side_effect = failure
            with self.assertRaisesMessage(CertificateChangeError, "could not be stored") as caught:
                self.install(parsed_certificate()[0])

        self.assertIn("AccessDeniedException", str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        self.assertFalse(MicrosoftGraphCertificate.objects.exists())

    def test_an_application_change_during_the_test_leaves_the_stored_version_unpinned(self):
        stale = MicrosoftGraphProviderConfig.objects.get(pk=self.config.pk)
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(
            client_id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
        )

        with self.assertRaisesMessage(CertificateChangeError, lifecycle.APPLICATION_CHANGED):
            self.install(parsed_certificate()[0], config=stale)

        self.assertEqual(len(stored_versions()), 1)  # an orphan nothing reads
        self.assertFalse(MicrosoftGraphCertificate.objects.exists())

    def test_a_config_without_a_saved_application_is_refused(self):
        for config in (MicrosoftGraphProviderConfig(tenant_id=TENANT_ID, client_id=CLIENT_ID), self.unsaved_app()):
            with self.subTest(config=config.tenant_id):
                with self.assertRaisesMessage(CertificateChangeError, lifecycle.APPLICATION_REQUIRED):
                    self.install(parsed_certificate()[0], config=config)
        self.assertEqual(self.fake.requests, [])
