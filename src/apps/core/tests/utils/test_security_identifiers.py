"""Tests for the Entra / Exchange identifier validators in ``apps.core.utils.security``.

``tenant_id`` and the sender mailbox become URL path segments of Microsoft endpoints, so these checks are the
last line of defence against path, query and header injection through values entered in the admin or the database.
"""

from django.test import SimpleTestCase

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid, is_plain_address

GUID = "72f988bf-86f1-41af-91ab-2d7cd011db47"
# 63 characters is the longest DNS label; 253 characters is the longest DNS name.
LONGEST_LABEL = "a" * 63
LONGEST_NAME = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61])


class IsGuidTests(SimpleTestCase):
    def test_accepts_canonical_guids_in_any_letter_case(self):
        values = [
            GUID,
            GUID.upper(),
            "72F988bf-86F1-41af-91AB-2d7cd011DB47",
            "00000000-0000-0000-0000-000000000000",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(is_guid(value))

    def test_rejects_everything_that_is_not_a_canonical_guid(self):
        values = [
            "",
            None,
            0,
            123,
            "not-a-guid",
            GUID.replace("-", ""),
            "{" + GUID + "}",
            "urn:uuid:" + GUID,
            GUID + "\n",
            "\n" + GUID,
            " " + GUID,
            GUID + " ",
            GUID[:-1],
            GUID + "0",
            "g" + GUID[1:],
            "\N{ARABIC-INDIC DIGIT THREE}" + GUID[1:],  # not an ASCII hex digit, although int() accepts it
            GUID.replace("-", "_"),
            GUID + "-0000",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_guid(value))


class IsEntraTenantTests(SimpleTestCase):
    def test_accepts_tenant_guids_and_dns_names(self):
        values = [
            GUID,
            GUID.upper(),
            "contoso.onmicrosoft.com",
            "Contoso.OnMicrosoft.com",
            "ucmerced.edu",
            "my-company.onmicrosoft.com",
            "sub.domain.example.co.uk",
            "xn--bcher-kva.example",
            "123.example.com",
            "a.b",
            LONGEST_LABEL + ".com",
            LONGEST_NAME,
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(is_entra_tenant(value))

    def test_rejects_the_multi_tenant_aliases_which_cannot_issue_app_only_tokens(self):
        for value in ("common", "organizations", "consumers"):
            with self.subTest(value=value):
                self.assertFalse(is_entra_tenant(value))

    def test_rejects_values_that_could_change_the_url_path_or_query(self):
        values = [
            "../x.com",
            "..",
            "a/b",
            "x.com/evil",
            "x.com\\evil",
            "x.com?y=1",
            "x.com#frag",
            "x.com%2F",
            "x.com:443",
            "user@x.com",
            "x com",
            "x.com\n",
            "\nx.com",
            " x.com",
            "x.com ",
            GUID + "\n",
            GUID[:-1],
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_entra_tenant(value))

    def test_rejects_malformed_dns_names(self):
        values = [
            "",
            None,
            "-a.com",
            "a-.com",
            "a..com",
            ".com",
            "x.",
            "x.com.",
            "a_b.com",
            "b\N{LATIN SMALL LETTER U WITH DIAERESIS}cher.de",
            "a" * 64 + ".com",  # label longer than 63 characters
            LONGEST_NAME + "d",  # name longer than 253 characters
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_entra_tenant(value))


class IsExchangeMailboxTests(SimpleTestCase):
    def test_accepts_addresses_and_user_object_ids(self):
        values = [
            "user@contoso.com",
            "user+tag@contoso.com",
            "first.last@sub.contoso.com",
            "o'brien@contoso.com",
            "UPPER@CONTOSO.COM",
            GUID,
            GUID.upper(),
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(is_exchange_mailbox(value))

    def test_rejects_garbage(self):
        values = [
            "",
            None,
            "garbage",
            "user@",
            "@contoso.com",
            "user@@contoso.com",
            "a b@contoso.com",
            "user@contoso",
            "user@contoso..com",
            "user@-bad.com",
            "user@contoso.com, other@contoso.com",
            "Display Name <user@contoso.com>",
            GUID[:-1],
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_exchange_mailbox(value))

    def test_rejects_newline_injection(self):
        values = [
            "user@contoso.com\n",
            "\nuser@contoso.com",
            "user@contoso.com\nBcc: evil@example.com",
            "user@contoso.com\r\nSubject: forged",
            GUID + "\n",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_exchange_mailbox(value))


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
