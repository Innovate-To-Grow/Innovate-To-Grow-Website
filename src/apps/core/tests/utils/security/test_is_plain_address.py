from django.test import SimpleTestCase

from apps.core.tests.utils.security.test_security_identifiers import LONGEST_NAME
from apps.core.utils.security import is_plain_address


class IsPlainAddressTests(SimpleTestCase):
    """Bare ``local@domain`` addresses only: the inbox reply To / Cc come from a sender-controlled From header."""

    def test_accepts_ordinary_addresses(self):
        for value in (
            "ada@example.com",
            "First.Last+tag@mail.example.co.uk",
            "a_b-c=d@example.org",
            "o'brien@example.com",
            "r&d@example.com",
            "x@" + LONGEST_NAME,
        ):
            with self.subTest(value=value):
                self.assertTrue(is_plain_address(value))

    def test_rejects_quoted_names_comments_literals_and_markup_characters(self):
        values = [
            "",
            None,
            "ada",
            "@example.com",
            "ada@",
            '"ada"@example.com',
            '"ada <img src=x onerror=alert(1)>"@example.com',
            "Ada <ada@example.com>",
            "<ada@example.com>",
            "ada@example.com (Ada)",
            "ada lovelace@example.com",
            "ada..lovelace@example.com",
            ".ada@example.com",
            "ada.@example.com",
            "<script>@example.com",
            "ada@[192.0.2.1]",
            "ada@localhost",
            "ada@example.com\n",
            "ada@example.com\r\nBcc: evil@example.com",
            "ada@exa_mple.com",
            "ada@example.com.",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_plain_address(value))
