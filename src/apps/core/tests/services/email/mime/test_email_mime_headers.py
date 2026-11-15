"""Caller-supplied MIME headers: a name that is not an RFC 5322 field name is refused before the protected-header
check, so whitespace cannot slip a protected name (the credential-mail tag among them) into the message."""

from django.test import SimpleTestCase

from apps.core.services.email import EmailMessage, PermanentEmailDeliveryError
from apps.core.services.email.mime import MAIL_CLASS_HEADER, build_mime_message


def build(headers, **values):
    message = EmailMessage(subject="Hello", to=("to@example.com",), text_body="Body", headers=headers, **values)
    return build_mime_message(message, from_email="from@example.com")


class HeaderNameTests(SimpleTestCase):
    def test_padded_or_folded_names_of_protected_headers_are_refused(self):
        for name in (f" {MAIL_CLASS_HEADER}", f"{MAIL_CLASS_HEADER} ", f"{MAIL_CLASS_HEADER}\t", "Sub ject", "To:"):
            with (
                self.subTest(name=repr(name)),
                self.assertRaisesMessage(PermanentEmailDeliveryError, "An email header is malformed."),
            ):
                build({name: "credential"})

    def test_names_outside_printable_ascii_are_refused(self):
        for name in ("", "X-Café", "X-Line\nBreak"):
            with self.subTest(name=repr(name)), self.assertRaises(PermanentEmailDeliveryError):
                build({name: "value"})

    def test_ordinary_custom_headers_still_pass(self):
        mime = build({"X-Campaign-Id": "42", "List-Unsubscribe": "<https://example.com/u>"})

        self.assertEqual((mime["X-Campaign-Id"], mime["List-Unsubscribe"]), ("42", "<https://example.com/u>"))

    def test_only_the_site_sets_the_credential_tag(self):
        self.assertEqual(build({}, keep_sent_copy=False)[MAIL_CLASS_HEADER], "credential")
        with self.assertRaisesMessage(PermanentEmailDeliveryError, "is managed by the delivery service"):
            build({MAIL_CLASS_HEADER.lower(): "credential"})
