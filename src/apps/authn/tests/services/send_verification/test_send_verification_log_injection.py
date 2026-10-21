from django.test import SimpleTestCase

from apps.authn.services.send_verification.metrics import _log_token, emit


class SendVerificationLogInjectionTests(SimpleTestCase):
    def test_log_tokens_escape_record_and_field_delimiters(self):
        self.assertEqual(
            _log_token("ok\r\nforged=true\tvalue\x1b[31m\u2028end\u202e\\n"),
            "ok\\r\\nforged\\u003dtrue\\u0009value\\u001b[31m\\u2028end\\u202e\\\\n",
        )

    def test_event_keys_and_values_cannot_forge_another_record(self):
        with self.assertLogs("apps.authn.send_verification", level="INFO") as logs:
            emit("test\nforged", **{"operation\r\n": "login\nadmin=true"})
        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertNotIn("\n", message)
        self.assertNotIn("\r", message)
        self.assertEqual(message, "send_verification.unknown ")

    def test_existing_plain_event_format_is_preserved(self):
        with self.assertLogs("apps.authn.send_verification", level="INFO") as logs:
            emit("send_finalized", status="provider_accepted", http_status=202, ignored=None)
        self.assertEqual(
            logs.records[0].getMessage(), "send_verification.send_finalized http_status=202 status=provider_accepted"
        )
