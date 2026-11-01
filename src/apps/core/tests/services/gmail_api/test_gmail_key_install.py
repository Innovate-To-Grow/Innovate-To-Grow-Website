"""The service-account key: checking the file in memory, the token test matrix, the store-then-pin order, and the
emergency removal."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import DeliveryRateState, EmailServiceConfig, GmailApiProviderConfig
from apps.core.services.credential_store import CredentialStoreError, get_store
from apps.core.services.email.gmail.key import install, parsing, removal, stored_key
from apps.core.services.email.gmail.key.install import KeyChangeError
from apps.core.services.email.gmail.key.parsing import KeyInputError, parse_key
from apps.core.tests.gmail_api_helpers import (
    CLIENT_ID,
    KEY_ID,
    SERVICE_ACCOUNT,
    SUBJECT,
    FakePost,
    ec_pem,
    key_json,
    make_config,
    make_email_config,
    pem,
    reset_gmail_state,
    rsa_key,
    token_error,
    token_response,
)
from apps.event.tests.helpers import make_superuser

OTHER_ACCOUNT = "i2g-other@i2g-mail-project.iam.gserviceaccount.com"
OTHER_KEY_ID = "fedcba9876543210fedcba9876543210fedcba98"


class KeyParsingTests(TestCase):
    def test_a_console_and_a_gcloud_key_file_both_parse(self):
        for token_uri in parsing.TOKEN_URIS:
            with self.subTest(token_uri=token_uri):
                parsed = parse_key(key_json(token_uri=token_uri))
                self.assertEqual(
                    (parsed.client_email, parsed.client_id, parsed.key_id), (SERVICE_ACCOUNT, CLIENT_ID, KEY_ID)
                )
                self.assertEqual(set(parsed.payload), set(stored_key.PAYLOAD_FIELDS))
                self.assertNotIn("token_uri", parsed.payload)
                self.assertNotIn("PRIVATE", repr(parsed))

    def test_bytes_with_a_byte_order_mark_parse(self):
        self.assertEqual(parse_key(b"\xef\xbb\xbf" + key_json().encode()).key_id, KEY_ID)

    def test_the_validation_matrix_refuses_with_fixed_text(self):
        duplicate = key_json()[:-1] + ', "type": "service_account"}'
        cases = {
            "not json": ("{nope", parsing.NOT_JSON),
            "NaN": (key_json().replace('"googleapis.com"', "NaN"), parsing.NOT_JSON),
            "duplicate": (duplicate, parsing.DUPLICATE_FIELD),
            "array": ("[]", parsing.NOT_OBJECT),
            "oversize": ("x" * 16_385, parsing.TOO_LARGE),
            "not utf-8": (b"\xff\xfe{}", parsing.NOT_TEXT),
            "authorized user": (key_json(type="authorized_user"), parsing.NOT_SERVICE_ACCOUNT),
            "external account": (key_json(type="external_account"), parsing.NOT_SERVICE_ACCOUNT),
            "missing client_id": (key_json(client_id=None), parsing.MISSING_FIELD.format(field="client_id")),
            "missing key": (key_json(private_key=None), parsing.MISSING_FIELD.format(field="private_key")),
            "ec key": (key_json(private_key=ec_pem()), "Google service-account keys are RSA keys"),
            "1024-bit key": (key_json(private_key=pem(rsa_key(1024))), "smaller than the site accepts"),
            "encrypted key": (key_json(private_key=pem(password=b"passphrase-x")), "could not be read"),
            "other token_uri": (key_json(token_uri="https://evil.example/token"), parsing.BAD_TOKEN_URI),
            "not a service account": (key_json(client_email="me@gmail.com"), parsing.BAD_EMAIL),
            "compute account": (key_json(client_email="123-compute@developer.gserviceaccount.com"), parsing.BAD_EMAIL),
            "project mismatch": (key_json(project_id="another-project"), parsing.PROJECT_MISMATCH),
            "domain-scoped": (key_json(project_id="example.com:i2g"), parsing.DOMAIN_SCOPED),
            "client id": (key_json(client_id="12ab"), parsing.BAD_CLIENT_ID),
            "key id": (key_json(private_key_id="XYZ"), parsing.BAD_KEY_ID),
            "universe": (key_json(universe_domain="example.com"), parsing.BAD_UNIVERSE),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name), self.assertRaises(KeyInputError) as caught:
                parse_key(data)
            self.assertIn(message, caught.exception.message)
            self.assertIsNone(caught.exception.__cause__)

    def test_no_message_contains_the_submitted_text(self):
        secret = "SENTINEL-super-secret-value"
        for data in (key_json(client_id=secret), key_json(token_uri=secret), f'{{"{secret}": 1, "{secret}": 2}}'):
            with self.subTest(data=data[:40]), self.assertRaises(KeyInputError) as caught:
                parse_key(data)
            self.assertNotIn(secret, str(caught.exception))


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


class RemovalTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.actor = make_superuser()

    def test_removal_unpins_deactivates_and_can_switch_to_ses(self):
        config = make_config()
        email = make_email_config()
        with patch.object(EmailServiceConfig, "validate_activation"):
            result = removal.remove_key(config, reason="Key leaked", actor=self.actor, switch_to_ses=True)
        config.refresh_from_db()
        self.assertTrue(result.provider_switched)
        self.assertFalse(config.is_active or config.key_configured or config.key_installed_at)
        self.assertEqual(EmailServiceConfig.objects.get(pk=email.pk).provider, "ses")
        self.assertIn("Key leaked", LogEntry.objects.get().change_message)

    def test_removal_without_a_ready_ses_keeps_the_provider(self):
        config = make_config()
        email = make_email_config()
        result = removal.remove_key(config, reason="Rotation gone wrong", actor=self.actor, switch_to_ses=True)
        self.assertFalse(result.provider_switched)
        self.assertEqual(EmailServiceConfig.objects.get(pk=email.pk).provider, "gmail")

    def test_nothing_to_remove(self):
        with self.assertRaises(KeyChangeError):
            removal.remove_key(make_config(active=False, key=False), reason="x", actor=self.actor)
