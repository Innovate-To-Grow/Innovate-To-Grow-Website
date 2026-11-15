from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.analytics import (
    PATH_MAX_BYTES,
    PATH_MAX_LENGTH,
    REFERRER_MAX_LENGTH,
    SESSION_KEY_MAX_LENGTH,
    USER_AGENT_MAX_LENGTH,
    VISITOR_ID_MAX_LENGTH,
    bounded_page_view,
)
from apps.cms.services.analytics.record import clean_ip_address, clean_session_key


class BoundedPageViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_text_is_cut_at_its_limit_and_loses_nul_characters(self):
        bounded = bounded_page_view(
            {"path": "/a\x00b" + "p" * 3000, "referrer": "r" * 3000, "user_agent": "Mozilla\x00/5.0 " + "u" * 600}
        )

        self.assertEqual(bounded["path"], ("/ab" + "p" * 3000)[:PATH_MAX_LENGTH])
        self.assertEqual(bounded["referrer"], "r" * REFERRER_MAX_LENGTH)
        self.assertEqual(bounded["user_agent"], ("Mozilla/5.0 " + "u" * 600)[:USER_AGENT_MAX_LENGTH])
        self.assertEqual(len(bounded["user_agent"]), 512)

    def test_lone_surrogates_are_removed(self):
        """No database encoding can store one; left in, the whole batch would fail to encode."""
        bounded = bounded_page_view(
            {"path": "/a\ud800b", "referrer": "https://example.com/\udfff", "user_agent": "Mozilla\ud83d/5.0"}
        )

        self.assertEqual(bounded, {"path": "/ab", "referrer": "https://example.com/", "user_agent": "Mozilla/5.0"})
        for value in bounded.values():
            value.encode("utf-8")

    def test_only_the_indexed_path_is_bounded_in_bytes(self):
        bounded = bounded_page_view({"path": "é" * 3000, "referrer": "é" * 3000, "user_agent": "é" * 3000})

        self.assertEqual(bounded["path"], "é" * (PATH_MAX_BYTES // 2))
        self.assertEqual(bounded["referrer"], "é" * REFERRER_MAX_LENGTH)
        self.assertEqual(bounded["user_agent"], "é" * USER_AGENT_MAX_LENGTH)

    def test_values_within_their_limits_are_unchanged(self):
        member = object()
        data = {
            "path": "/about",
            "referrer": "https://example.com/",
            "user_agent": "Mozilla/5.0",
            "ip_address": "169.236.0.10",
            "visitor_id": "3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f",
            "session_key": "k" * 32,
            "member": member,
        }

        bounded = bounded_page_view(data)

        self.assertEqual(bounded, data)
        self.assertIs(bounded["member"], member)
        self.assertIsNot(bounded, data)

    def test_the_input_is_not_modified_and_absent_fields_stay_absent(self):
        data = {"path": "/", "user_agent": "u" * 600}

        bounded = bounded_page_view(data)

        self.assertEqual(data, {"path": "/", "user_agent": "u" * 600})
        self.assertEqual(bounded, {"path": "/", "user_agent": "u" * 512})

    def test_text_that_is_not_a_string_becomes_empty(self):
        bounded = bounded_page_view({"path": None, "referrer": 7, "user_agent": ["Mozilla"], "session_key": None})

        self.assertEqual(bounded, {"path": "", "referrer": "", "user_agent": "", "session_key": ""})

    def test_a_malformed_visitor_id_becomes_null(self):
        self.assertIsNone(bounded_page_view({"visitor_id": "v" * (VISITOR_ID_MAX_LENGTH + 1)})["visitor_id"])
        self.assertIsNone(bounded_page_view({"visitor_id": "has space"})["visitor_id"])
        self.assertIsNone(bounded_page_view({"visitor_id": None})["visitor_id"])
        self.assertEqual(bounded_page_view({"visitor_id": "v" * VISITOR_ID_MAX_LENGTH})["visitor_id"], "v" * 64)

    def test_session_keys(self):
        self.assertEqual(clean_session_key("k" * 32), "k" * 32)
        self.assertEqual(clean_session_key("k" * SESSION_KEY_MAX_LENGTH), "k" * 64)
        self.assertEqual(clean_session_key("k" * (SESSION_KEY_MAX_LENGTH + 1)), "")
        self.assertEqual(clean_session_key("with\x00nul"), "")
        self.assertEqual(clean_session_key("with\ud800surrogate"), "")
        self.assertEqual(clean_session_key(""), "")
        self.assertEqual(clean_session_key(None), "")
        self.assertEqual(clean_session_key(12345678), "")

    def test_ip_addresses(self):
        for value, expected in (
            ("203.0.113.50", "203.0.113.50"),
            (" 203.0.113.50 ", "203.0.113.50"),
            ("2001:db8::1", "2001:db8::1"),
            ("2001:0DB8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
            ("::1", "::1"),
            ("fe80::1%eth0", None),
            ("203.0.113.50, 10.0.0.1", None),
            ("203.0.113", None),
            ("256.1.1.1", None),
            ("a:b", None),
            ("localhost", None),
            ("", None),
            ("1" * 46, None),
            ("9" * 5000, None),
            (None, None),
            (2130706433, None),
            (b"127.0.0.1", None),
        ):
            with self.subTest(value=value):
                self.assertEqual(clean_ip_address(value), expected)
