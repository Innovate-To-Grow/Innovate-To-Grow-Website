"""``GMAIL_API``: the defaults, the ``GMAIL_API_OVERRIDES`` JSON, and the import-time validation."""

import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.base.integrations.gmail_api import DEFAULTS
from config.settings.base.integrations.gmail_api.validation import load_gmail_api


class GmailApiSettingsTests(SimpleTestCase):
    def test_documented_defaults(self):
        self.assertEqual(settings.GMAIL_API, DEFAULTS)
        self.assertEqual(DEFAULTS["max_recipients_per_message"], 500)
        self.assertEqual(DEFAULTS["max_message_bytes"], 25_000_000)
        self.assertEqual(DEFAULTS["upload_max_bytes"], 36_700_160)
        self.assertEqual(DEFAULTS["min_rsa_key_bits"], 2048)
        self.assertLessEqual(DEFAULTS["assertion_lifetime_seconds"], 3600)

    def test_an_override_replaces_an_existing_key(self):
        values = load_gmail_api(DEFAULTS, json.dumps({"request_timeout_seconds": 20}))
        self.assertEqual(values["request_timeout_seconds"], 20)
        self.assertEqual(DEFAULTS["request_timeout_seconds"], 15)

    def test_bad_overrides_stop_the_import(self):
        for raw in (
            "not json",
            "[1]",
            json.dumps({"unknown": 1}),
            json.dumps({"request_timeout_seconds": 0}),
            json.dumps({"request_timeout_seconds": True}),
            json.dumps({"request_timeout_seconds": 1.5}),
            json.dumps({"assertion_lifetime_seconds": 3601}),
            json.dumps({"token_expiry_margin_seconds": 3600}),
            json.dumps({"max_message_bytes": 36_700_161}),
        ):
            with self.subTest(raw=raw), self.assertRaises(ImproperlyConfigured):
                load_gmail_api(DEFAULTS, raw)

    def test_blank_overrides_keep_the_defaults(self):
        self.assertEqual(load_gmail_api(DEFAULTS, "  "), DEFAULTS)

    def test_the_key_has_a_credential_store_secret(self):
        self.assertEqual(
            settings.CREDENTIAL_STORE_SECRETS["gmail_api_service_account_key"],
            "itg/backend/gmail-api/service-account-key",
        )
