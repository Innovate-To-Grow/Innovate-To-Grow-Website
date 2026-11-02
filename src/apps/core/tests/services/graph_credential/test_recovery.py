"""Rolling back to the previous Microsoft Graph certificate, and the emergency removal of both."""

import datetime

import jwt
from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphCertificate
from apps.core.services.credential_store import get_store, memory
from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.services.email.graph import auth
from apps.core.services.email.graph.access import credential_for
from apps.core.services.email.graph.credential import recovery, stored_key
from apps.core.services.email.graph.credential.lifecycle import CertificateChangeError, install_certificate
from apps.core.services.email.graph.credential.recovery import remove_certificates, rollback_certificate
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.graph_credential.helpers import (
    LifecycleFixtureMixin,
    entra_rejection,
    make_superuser,
    parsed_certificate,
)

State = MicrosoftGraphCertificate.State
SENDER = "i2g@contoso.com"


class RecoveryFixtureMixin(LifecycleFixtureMixin):
    def setUp(self):
        super().setUp()
        self.actor = make_superuser()
        self.config = create_graph_config(name="Graph", is_active=True, certificate=False, scope=(SENDER,))
        self.first = install_certificate(self.config, parsed_certificate()[0], actor=self.actor)
        self.second = install_certificate(self.config, parsed_certificate(key_index=1)[0], actor=self.actor)
        self.script()

    def states(self):
        return dict(MicrosoftGraphCertificate.objects.values_list("pk", "state"))


class RollbackTests(RecoveryFixtureMixin, TestCase):
    def test_rollback_swaps_current_and_previous_after_entra_accepts_the_previous_key(self):
        with self.captureOnCommitCallbacks(execute=True):
            restored = rollback_certificate(self.config, actor=self.actor)

        self.assertEqual(restored, self.first)
        self.assertEqual(self.states(), {self.first.pk: State.CURRENT, self.second.pk: State.PREVIOUS})
        (request,) = self.fake.token_requests
        assertion = request.body.decode().split("client_assertion=")[1].split("&")[0]
        self.assertEqual(jwt.get_unverified_header(assertion)["x5t#S256"], self.first.x5t_s256)
        self.assertEqual(credential_for(self.config).key_version_id, self.first.store_version_id)
        self.assertEqual(get_store().describe(stored_key.KEY_NAME).current_version_id, self.first.store_version_id)
        entry = LogEntry.objects.filter(object_id=str(self.config.pk)).latest("action_time")
        self.assertIn(
            f"Rolled back to Microsoft Graph certificate (SHA-1 {self.first.sha1_thumbprint}", entry.change_message
        )

    def test_rolling_back_twice_returns_to_the_newer_certificate(self):
        rollback_certificate(self.config)
        self.script()

        rollback_certificate(self.config)

        self.assertEqual(self.states(), {self.first.pk: State.PREVIOUS, self.second.pk: State.CURRENT})

    def test_rollback_refuses_without_a_previous_certificate(self):
        MicrosoftGraphCertificate.objects.filter(pk=self.first.pk).update(state=State.REMOVED)

        with self.assertRaisesMessage(CertificateChangeError, recovery.NO_PREVIOUS):
            rollback_certificate(self.config)
        self.assertEqual(self.fake.requests, [])

    def test_rollback_refuses_a_previous_certificate_entra_no_longer_accepts(self):
        self.script(token=entra_rejection(700027))

        with self.assertRaisesMessage(CertificateChangeError, "was not restored"):
            rollback_certificate(self.config)

        self.assertEqual(self.states(), {self.first.pk: State.PREVIOUS, self.second.pk: State.CURRENT})

    def test_rollback_refuses_an_expired_previous_certificate(self):
        MicrosoftGraphCertificate.objects.filter(pk=self.first.pk).update(
            not_after=timezone.now() - datetime.timedelta(minutes=1)
        )

        with self.assertRaisesMessage(CertificateChangeError, recovery.PREVIOUS_NOT_VALID):
            rollback_certificate(self.config)

    def test_rollback_refuses_when_the_previous_key_cannot_be_read(self):
        memory.reset()

        with self.assertRaisesMessage(CertificateChangeError, "installed private key could not be read") as caught:
            rollback_certificate(self.config)

        self.assertIn("ResourceNotFoundException", str(caught.exception))
        self.assertEqual(self.fake.requests, [])

    def test_rollback_refuses_when_the_certificates_changed_meanwhile(self):
        stale_previous = self.config.previous_certificate
        install_certificate(self.config, parsed_certificate(key_index=2)[0])
        check = recovery.entra_check.EntraCheckResult(recovery.entra_check.OK)

        with self.assertRaisesMessage(CertificateChangeError, recovery.CHANGED_MEANWHILE):
            recovery._swap(self.config, stale_previous, self.second, check, None)


class RemoveTests(RecoveryFixtureMixin, TestCase):
    def test_remove_unpins_both_certificates_without_calling_the_store_or_entra(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = remove_certificates(self.config, reason="Key exposed in a screenshot", actor=self.actor)

        self.assertEqual(result, recovery.RemovalResult(removed=2, provider_switched=False))
        self.assertEqual(self.states(), {self.first.pk: State.REMOVED, self.second.pk: State.REMOVED})
        self.second.refresh_from_db()
        self.assertEqual(self.second.removal_note, "Key exposed in a screenshot")
        self.assertIsNotNone(self.second.removed_at)
        self.assertEqual(self.fake.requests, [])
        self.assertFalse(self.config.is_configured)
        with self.assertRaises(PermanentEmailDeliveryError):
            credential_for(self.config)
        entry = LogEntry.objects.filter(object_id=str(self.config.pk)).latest("action_time")
        self.assertIn(
            "Removed 2 Microsoft Graph certificate(s). Reason: Key exposed in a screenshot", entry.change_message
        )

    def test_remove_leaves_the_stored_versions_and_labels_alone(self):
        before = get_store().describe(stored_key.KEY_NAME)

        remove_certificates(self.config, reason="Rotating after an incident")

        self.assertEqual(get_store().describe(stored_key.KEY_NAME), before)

    def test_remove_clears_this_process_token_cache_on_commit(self):
        auth.get_access_token(credential_for(self.config))
        self.assertTrue(auth._cache)

        with self.captureOnCommitCallbacks(execute=True):
            remove_certificates(self.config, reason="Incident")

        self.assertEqual(auth._cache, {})

    def test_remove_requires_a_reason(self):
        for reason in ("", "   ", None):
            with self.subTest(reason=reason):
                with self.assertRaisesMessage(CertificateChangeError, recovery.REASON_REQUIRED) as caught:
                    remove_certificates(self.config, reason=reason)
                self.assertEqual(caught.exception.field, "reason")
        self.assertEqual(self.states()[self.second.pk], State.CURRENT)

    def test_remove_can_switch_the_sending_provider_to_ses_when_ses_is_ready(self):
        email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )

        result = remove_certificates(self.config, reason="Incident", switch_to_ses=True, actor=self.actor)

        self.assertTrue(result.provider_switched)
        email.refresh_from_db()
        self.assertEqual(email.provider, "ses")
        entry = LogEntry.objects.filter(object_id=str(self.config.pk)).latest("action_time")
        self.assertIn("Email provider switched to AWS SES", entry.change_message)

    def test_remove_still_removes_when_ses_is_not_ready_and_says_so(self):
        email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)

        result = remove_certificates(self.config, reason="Incident", switch_to_ses=True)

        self.assertEqual(result, recovery.RemovalResult(removed=2, provider_switched=False))
        email.refresh_from_db()
        self.assertEqual(email.provider, "graph")

    def test_an_inactive_config_never_switches_the_provider(self):
        email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        self.config.is_active = False
        self.config.save()

        self.assertFalse(remove_certificates(self.config, reason="Old config", switch_to_ses=True).provider_switched)
        email.refresh_from_db()
        self.assertEqual(email.provider, "graph")

    def test_a_new_certificate_can_be_installed_after_removal(self):
        remove_certificates(self.config, reason="Incident")

        certificate = install_certificate(self.config, parsed_certificate(key_index=2)[0])

        self.assertEqual(self.config.current_certificate, certificate)
        self.assertIsNone(self.config.previous_certificate)
