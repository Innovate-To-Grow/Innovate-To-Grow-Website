from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import DeliveryRateState, GmailApiProviderConfig
from apps.core.services.credential_store import CredentialStoreError, get_store
from apps.core.services.email.gmail.key import install
from apps.core.services.email.gmail.key.install import KeyChangeError
from apps.core.services.email.gmail.service_account import stored_key
from apps.core.services.email.gmail.service_account.parsing import parse_key
from apps.core.tests.gmail_api_helpers import (
    CLIENT_ID,
    KEY_ID,
    SERVICE_ACCOUNT,
    SUBJECT,
    FakePost,
    key_json,
    make_config,
    make_email_config,
    pem,
    reset_gmail_state,
    rsa_key,
    token_error,
    token_response,
)
from apps.core.tests.services.gmail_api.key.test_gmail_key_install import OTHER_ACCOUNT, OTHER_KEY_ID
from apps.event.tests.helpers import make_superuser


class InstallMatrixTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.actor = make_superuser()
        self.config = make_config(active=False, key=False)

    def install(self, *answers, config=None, **key_fields):
        self.post = FakePost(*answers).install(self)
        return install.install_key(config or self.config, parse_key(key_json(**key_fields)), actor=self.actor)

    def stored_versions(self):
        try:
            return get_store().describe(stored_key.KEY_NAME).version_stages
        except CredentialStoreError:
            return ()

    def test_a_first_install_with_an_issued_token_stores_pins_and_records_public_facts(self):
        test = self.install(token_response())
        self.config.refresh_from_db()
        self.assertEqual(test.outcome, install.ISSUED)
        self.assertTrue(self.config.key_configured)
        self.assertEqual((self.config.service_account_email, self.config.key_id), (SERVICE_ACCOUNT, KEY_ID))
        self.assertIsNotNone(self.config.key_installed_at)
        self.assertIsNone(self.config.access_checked_at)
        self.assertFalse(self.config.is_active)
        stored = get_store().read(
            stored_key.KEY_NAME, arn=self.config.key_secret_ref, version_id=self.config.key_version_id
        )
        self.assertEqual(set(stored), set(stored_key.PAYLOAD_FIELDS))
        entry = LogEntry.objects.get()
        self.assertIn(f"key id {KEY_ID}", entry.change_message)
        self.assertNotIn("PRIVATE KEY", entry.change_message)
        self.assertEqual(self.post.paths(), [("oauth2.googleapis.com", "/token")])  # the token test, nothing sent

    def test_a_first_install_while_delegation_is_pending_is_kept_inactive(self):
        for code in ("unauthorized_client", "access_denied"):
            with self.subTest(code=code):
                reset_gmail_state()
                test = self.install(token_error(code, "Unauthorized client or scope in request."))
                self.assertEqual(test.outcome, install.PENDING)
                self.assertIn(CLIENT_ID, test.describe())
                self.config.refresh_from_db()
                self.assertTrue(self.config.key_configured)
                self.assertFalse(self.config.is_active)
                GmailApiProviderConfig.objects.filter(pk=self.config.pk).update(key_secret_ref="", key_version_id="")
                self.config.refresh_from_db()

    def test_a_first_install_refused_for_the_signature_writes_nothing(self):
        for answer in (
            token_error("invalid_grant", "Invalid JWT Signature."),
            token_error("disabled_client", "The OAuth client was disabled."),
            token_error("deleted_client"),
            token_error("temporarily_unavailable"),
        ):
            with self.subTest(answer=answer.body), self.assertRaises(KeyChangeError) as caught:
                self.install(answer)
            self.assertIn("Nothing was changed", caught.exception.message)
            self.config.refresh_from_db()
            self.assertFalse(self.config.key_configured)
            self.assertEqual(self.stored_versions(), ())
            self.assertFalse(LogEntry.objects.exists())

    def test_a_rotation_must_get_a_token(self):
        self.install(token_response())
        self.config.refresh_from_db()
        pinned = self.config.key_version_id
        with self.assertRaises(KeyChangeError) as caught:
            self.install(
                token_error("unauthorized_client"), private_key_id=OTHER_KEY_ID, private_key=pem(rsa_key(3072))
            )
        self.assertIn("same service account", caught.exception.message)
        self.config.refresh_from_db()
        self.assertEqual(self.config.key_version_id, pinned)
        self.install(token_response(), private_key_id=OTHER_KEY_ID, private_key=pem(rsa_key(3072)))
        self.config.refresh_from_db()
        self.assertNotEqual(self.config.key_version_id, pinned)
        self.assertEqual(self.config.key_id, OTHER_KEY_ID)

    def test_another_service_account_while_gmail_sends_must_get_a_token(self):
        config = make_config()
        make_email_config()
        with self.assertRaises(KeyChangeError) as caught:
            self.install(token_error("unauthorized_client"), config=config, client_email=OTHER_ACCOUNT)
        self.assertIn("Email is sent through the Gmail API", caught.exception.message)
        self.install(token_response(), config=config, client_email=OTHER_ACCOUNT)
        config.refresh_from_db()
        self.assertEqual(config.service_account_email, OTHER_ACCOUNT)
        self.assertTrue(config.subjects.get().verified_at is None)

    def test_the_from_address_must_be_listed_first(self):
        GmailApiProviderConfig.objects.get(pk=self.config.pk).subjects.all().delete()
        with self.assertRaises(KeyChangeError) as caught:
            self.install(token_response())
        self.assertIn(SUBJECT, caught.exception.message)
        self.assertEqual(self.post.calls, [])

    def test_a_store_failure_leaves_the_database_unchanged(self):
        with patch.object(stored_key, "store_key", side_effect=CredentialStoreError("refused", code="AccessDenied")):
            with self.assertRaises(KeyChangeError) as caught:
                self.install(token_response())
        self.assertIn("could not be stored", caught.exception.message)
        self.config.refresh_from_db()
        self.assertFalse(self.config.key_configured)

    def test_a_database_failure_after_the_store_write_keeps_the_old_pin_readable(self):
        self.install(token_response())
        self.config.refresh_from_db()
        old = (self.config.key_secret_ref, self.config.key_version_id)
        with patch.object(install, "record", side_effect=DatabaseError("boom")), self.assertRaises(DatabaseError):
            self.install(token_response(), private_key_id=OTHER_KEY_ID, private_key=pem(rsa_key(3072)))
        self.config.refresh_from_db()
        self.assertEqual((self.config.key_secret_ref, self.config.key_version_id), old)
        key = stored_key.read_key(arn=old[0], version_id=old[1], client_email=SERVICE_ACCOUNT, key_id=KEY_ID)
        self.assertEqual(key.key_size, 2048)

    def test_a_new_key_lets_the_next_send_probe_a_refused_credentials_breaker(self):
        far = timezone.now() + timedelta(days=1)
        state = DeliveryRateState.objects.create(
            channel="gmail_api_send",
            identity=SUBJECT,
            cooldown_group=f"gmail_api:{SUBJECT}",
            breaker_state=DeliveryRateState.BreakerState.OPEN,
            breaker_reason="auth",
            breaker_retry_at=far,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.install(token_response())
        state.refresh_from_db()
        self.assertLess(state.breaker_retry_at, far)

    def test_installing_the_same_key_twice_reuses_its_stored_version(self):
        self.install(token_response())
        self.config.refresh_from_db()
        first = self.config.key_version_id
        self.install(token_response())
        self.config.refresh_from_db()
        self.assertEqual(self.config.key_version_id, first)
