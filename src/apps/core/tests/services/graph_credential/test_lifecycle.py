"""Installing a Microsoft Graph certificate: Entra test, key store write, pin, history and the store's labels."""

from unittest.mock import patch

import jwt
from django.contrib.admin.models import LogEntry
from django.test import TestCase, override_settings

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.credential_store import CURRENT_STAGE, PREVIOUS_STAGE, CredentialStoreError, get_store
from apps.core.services.email.graph import auth
from apps.core.services.email.graph.access import credential_for
from apps.core.services.email.graph.credential import entra_check, lifecycle, stored_key
from apps.core.services.email.graph.credential.lifecycle import CertificateChangeError, install_certificate
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, create_graph_config, private_key_lines
from apps.core.tests.services.graph_credential.helpers import (
    LifecycleFixtureMixin,
    entra_rejection,
    make_superuser,
    parsed_certificate,
    stored_versions,
)
from apps.core.tests.services.test_email_graph import ACCESS_TOKEN

State = MicrosoftGraphCertificate.State


class InstallTests(LifecycleFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.actor = make_superuser()
        self.config = create_graph_config(name="Graph", certificate=False, scope=("i2g@contoso.com",))

    def install(self, parsed, config=None):
        return install_certificate(config or self.config, parsed, actor=self.actor)

    def test_a_certificate_is_tested_stored_and_pinned_as_current(self):
        parsed, key = parsed_certificate()

        certificate = self.install(parsed)

        self.assertEqual(certificate.state, State.CURRENT)
        self.assertEqual((certificate.tenant_id, certificate.client_id), (TENANT_ID, CLIENT_ID))
        self.assertEqual(certificate.sha1_thumbprint, parsed.facts.sha1_thumbprint)
        self.assertEqual(certificate.certificate_pem, parsed.facts.certificate_pem)
        self.assertEqual((certificate.entra_check, certificate.entra_check_code), (entra_check.OK, ""))
        self.assertEqual(list(stored_versions()), [certificate.store_version_id])
        self.assertEqual(certificate.store_arn, get_store().describe(stored_key.KEY_NAME).arn)
        self.assertTrue(self.config.credential_configured)
        # One token request with the in-memory key, under the configured timeout; its token is not kept.
        (request,) = self.fake.token_requests
        self.assertEqual(request.timeout, 10)
        self.assertEqual(auth._cache, {})

    @override_settings(GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS=4)
    def test_the_entra_test_uses_the_configured_timeout(self):
        self.install(parsed_certificate()[0])

        self.assertEqual(self.fake.token_requests[0].timeout, 4)

    def test_the_installed_certificate_signs_the_next_token_request(self):
        certificate = self.install(parsed_certificate()[0])
        self.script()

        self.assertEqual(auth.get_access_token(credential_for(self.config)), ACCESS_TOKEN)

        assertion = self.fake.token_requests[0].body.decode().split("client_assertion=")[1].split("&")[0]
        self.assertEqual(jwt.get_unverified_header(assertion)["x5t#S256"], certificate.x5t_s256)

    def test_history_names_the_certificate_and_never_the_key(self):
        parsed, key = parsed_certificate()

        certificate = self.install(parsed)

        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        self.assertEqual(entry.user_id, self.actor.pk)
        self.assertIn(certificate.sha1_thumbprint, entry.change_message)
        self.assertIn(certificate.store_version_id, entry.change_message)
        self.assertIn(f"{certificate.not_after:%Y-%m-%d}", entry.change_message)
        for line in private_key_lines(key):
            self.assertNotIn(line, entry.change_message)

    def test_each_install_keeps_one_previous_and_retires_the_one_before(self):
        first = self.install(parsed_certificate()[0])
        second = self.install(parsed_certificate(key_index=1)[0])
        third = self.install(parsed_certificate(key_index=2)[0])

        states = dict(MicrosoftGraphCertificate.objects.values_list("pk", "state"))
        self.assertEqual(states, {first.pk: State.REMOVED, second.pk: State.PREVIOUS, third.pk: State.CURRENT})
        first.refresh_from_db()
        self.assertEqual(first.removal_note, lifecycle.REPLACED_NOTE)
        self.assertIsNotNone(first.removed_at)
        self.assertEqual(len(stored_versions()), 3)

    def test_a_certificate_without_a_key_re_issues_the_installed_key_without_a_new_version(self):
        first = self.install(parsed_certificate()[0])

        with patch.object(stored_key, "store_key", wraps=stored_key.store_key) as store_key:
            reissued = self.install(parsed_certificate(with_key=False)[0])

        store_key.assert_not_called()
        self.assertEqual(reissued.store_version_id, first.store_version_id)
        self.assertNotEqual(reissued.x5t_s256, first.x5t_s256)
        self.assertEqual(self.config.previous_certificate, first)

    def test_a_certificate_without_a_key_needs_an_installed_certificate_with_that_key(self):
        with self.assertRaisesMessage(CertificateChangeError, lifecycle.NO_KEY_TO_REUSE) as caught:
            self.install(parsed_certificate(with_key=False)[0])
        self.assertEqual(caught.exception.field, "private_key")

        self.install(parsed_certificate()[0])
        with self.assertRaisesMessage(CertificateChangeError, lifecycle.KEY_REQUIRED) as caught:
            self.install(parsed_certificate(with_key=False, key_index=1)[0])
        self.assertEqual(caught.exception.field, "private_key")

    def test_installing_the_current_or_previous_certificate_again_is_refused(self):
        first, _ = parsed_certificate()
        second, _ = parsed_certificate(key_index=1)
        self.install(first)
        self.install(second)

        for parsed, message in ((second, lifecycle.ALREADY_CURRENT), (first, lifecycle.IS_PREVIOUS)):
            with self.subTest(message):
                with self.assertRaisesMessage(CertificateChangeError, message):
                    self.install(parsed)

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

    def unsaved_app(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(tenant_id="common")
        return MicrosoftGraphProviderConfig.objects.get(pk=self.config.pk)


class StoreLabelTests(LifecycleFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.config = create_graph_config(name="Graph", is_active=True, certificate=False)

    def test_the_active_config_moves_awscurrent_to_the_pinned_version_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            first = install_certificate(self.config, parsed_certificate()[0])
        with self.captureOnCommitCallbacks(execute=True):
            second = install_certificate(self.config, parsed_certificate(key_index=1)[0])

        description = get_store().describe(stored_key.KEY_NAME)
        self.assertEqual(description.current_version_id, second.store_version_id)
        self.assertIn(PREVIOUS_STAGE, description.stages_of(first.store_version_id))

    def test_an_inactive_config_never_moves_the_label(self):
        self.config.is_active = False
        self.config.save()
        with self.captureOnCommitCallbacks(execute=True):
            first = install_certificate(self.config, parsed_certificate()[0])
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            install_certificate(self.config, parsed_certificate(key_index=1)[0])

        self.assertEqual(callbacks, [])
        self.assertIn(CURRENT_STAGE, get_store().describe(stored_key.KEY_NAME).stages_of(first.store_version_id))

    def test_a_label_failure_is_logged_and_keeps_the_pin(self):
        with patch.object(lifecycle, "get_store") as get_store_mock:
            get_store_mock.return_value.move_current.side_effect = CredentialStoreError("refused", code="AccessDenied")
            with self.assertLogs(lifecycle.logger, "WARNING") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    certificate = install_certificate(self.config, parsed_certificate()[0])

        self.assertIn("AccessDenied", logs.output[0])
        self.assertEqual(self.config.current_certificate, certificate)
