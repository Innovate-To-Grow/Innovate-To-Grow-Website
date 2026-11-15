from cryptography import x509
from django.contrib.admin.models import LogEntry
from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphCertificate
from apps.core.services.email.graph.credential import lifecycle, recovery
from apps.core.tests.admin.service_credentials.graph_certificate.test_graph_certificate_pages import State
from apps.core.tests.graph_helpers import make_certificate
from apps.core.tests.services.graph_credential.helpers import entra_rejection, stored_versions
from apps.event.tests.helpers import make_admin

from .graph_certificate_pages import SENDER, CertificatePagesMixin, pem


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

    def test_core_staff_roll_back_like_a_superuser(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))

        response = self.client.post(self.url("rollback_certificate"), follow=True)

        self.assertContains(response, "Rolled back to the previous certificate")
        self.assertEqual(self.config.current_certificate, self.first)

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
