from django.test import SimpleTestCase

from apps.core.services.email.graph.transport.errors import graph_error_code, identity_error_code
from apps.core.tests.services.graph.errors.test_email_graph_errors import UNREADABLE_BODIES, as_body
from apps.core.tests.services.graph.provider.test_email_graph import RESPONSE_TEXT


class GraphErrorCodeTests(SimpleTestCase):
    def test_returns_the_top_level_error_code(self):
        body = as_body({"error": {"code": "ErrorSendAsDenied", "message": RESPONSE_TEXT}})

        self.assertEqual(graph_error_code(body), "ErrorSendAsDenied")

    def test_falls_back_to_the_inner_error_code_in_either_spelling(self):
        for key in ("innerError", "innererror"):
            with self.subTest(key=key):
                body = as_body({"error": {"message": RESPONSE_TEXT, key: {"code": "InnerCode"}}})

                self.assertEqual(graph_error_code(body), "InnerCode")

    def test_the_top_level_code_wins_over_the_inner_code(self):
        body = as_body({"error": {"code": "OuterCode", "innerError": {"code": "InnerCode"}}})

        self.assertEqual(graph_error_code(body), "OuterCode")

    def test_an_unsafe_top_level_code_falls_back_to_a_safe_inner_code(self):
        body = as_body({"error": {"code": "not a safe code", "innerError": {"code": "InnerCode"}}})

        self.assertEqual(graph_error_code(body), "InnerCode")

    def test_accepts_the_shortest_and_longest_allowed_codes(self):
        for code in ("ab", "a" + "b" * 63, "Error_Code.With-Chars9"):
            with self.subTest(length=len(code)):
                self.assertEqual(graph_error_code(as_body({"error": {"code": code}})), code)

    def test_rejects_codes_outside_the_allow_list(self):
        values = [
            "bad code",
            "bad\ncode",
            "<b>bold</b>",
            "",
            "x",  # too short
            "1startswithdigit",
            "a" * 65,  # too long
            "caf\N{LATIN SMALL LETTER E WITH ACUTE}",
            RESPONSE_TEXT + " with spaces",
        ]
        for code in values:
            with self.subTest(code=code):
                self.assertEqual(graph_error_code(as_body({"error": {"code": code}})), "")

    def test_rejects_codes_that_are_not_strings(self):
        for code in (123, True, None, ["ErrorCode"], {"code": "ErrorCode"}):
            with self.subTest(code=code):
                self.assertEqual(graph_error_code(as_body({"error": {"code": code}})), "")

    def test_ignores_an_error_or_inner_error_that_is_not_an_object(self):
        payloads = [
            {"error": "invalid_client"},
            {"error": ["ErrorCode"]},
            {"error": {"innerError": "InnerCode"}},
            {"error": {"innerError": ["InnerCode"]}},
            {"error": {"innerError": None}},
            {"message": "no error key"},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(graph_error_code(as_body(payload)), "")

    def test_unreadable_bodies_give_an_empty_code(self):
        for body in UNREADABLE_BODIES:
            with self.subTest(body=body):
                self.assertEqual(graph_error_code(body), "")


class IdentityErrorCodeTests(SimpleTestCase):
    def test_combines_the_oauth_error_with_the_first_aadsts_number(self):
        body = as_body({"error": "invalid_client", "error_codes": [7000215], "error_description": RESPONSE_TEXT})

        self.assertEqual(identity_error_code(body), "invalid_client AADSTS7000215")

    def test_only_the_first_error_number_is_used(self):
        body = as_body({"error": "invalid_grant", "error_codes": [50126, 50053]})

        self.assertEqual(identity_error_code(body), "invalid_grant AADSTS50126")

    def test_an_error_without_numbers_is_returned_alone(self):
        self.assertEqual(identity_error_code(as_body({"error": "invalid_scope"})), "invalid_scope")

    def test_numbers_without_a_usable_error_are_returned_without_a_leading_space(self):
        for payload in ({"error_codes": [7000215]}, {"error": "bad error!", "error_codes": [7000215]}):
            with self.subTest(payload=payload):
                self.assertEqual(identity_error_code(as_body(payload)), "AADSTS7000215")

    def test_accepts_the_largest_eight_digit_number(self):
        body = as_body({"error": "invalid_client", "error_codes": [99999999]})

        self.assertEqual(identity_error_code(body), "invalid_client AADSTS99999999")

    def test_ignores_numbers_that_are_not_plain_positive_integers(self):
        values = [[True], [False], [-5], [0], [10**8], [1.5], ["7000215"], [None], [[7000215]], [], "7000215", 7000215]
        for numbers in values:
            with self.subTest(error_codes=numbers):
                body = as_body({"error": "invalid_client", "error_codes": numbers})

                self.assertEqual(identity_error_code(body), "invalid_client")

    def test_unsafe_or_missing_errors_give_an_empty_code(self):
        for payload in ({"error": "bad error!"}, {"error": {"nested": True}}, {"error": None}, {}):
            with self.subTest(payload=payload):
                self.assertEqual(identity_error_code(as_body(payload)), "")

    def test_unreadable_bodies_give_an_empty_code(self):
        for body in UNREADABLE_BODIES:
            with self.subTest(body=body):
                self.assertEqual(identity_error_code(body), "")
