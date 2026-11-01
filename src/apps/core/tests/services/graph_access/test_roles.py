"""The access token's ``roles`` claim: read without trusting it, and judged against the approval."""

from django.test import SimpleTestCase, override_settings

from apps.core.services.email.graph.access_check import FAIL, INCONCLUSIVE, PASS, WARN
from apps.core.services.email.graph.access_check.roles import approved_roles, roles_result, token_roles
from apps.core.tests.services.graph_access.helpers import APPROVED, OIT_ROLES, jwt, token_with_roles


class TokenRolesTests(SimpleTestCase):
    def test_the_roles_claim_is_read_sorted_and_deduplicated(self):
        token = token_with_roles(("Mail.Send", "Mail.ReadWrite", "Mail.Send"))

        self.assertEqual(token_roles(token), ("Mail.ReadWrite", "Mail.Send"))

    def test_a_token_without_roles_claims_none(self):
        self.assertEqual(token_roles(token_with_roles(None)), ())

    def test_unreadable_tokens_and_claims_are_none_and_never_echoed(self):
        cases = {
            "opaque": "not-a-jwt",
            "two parts": "a.b",
            "bad base64": "a.!!!.c",
            "not json": "a.bm90IGpzb24.c",
            "a list payload": jwt(["Mail.Send"]),
            "roles not a list": jwt({"roles": "Mail.Send"}),
            "a non-string role": jwt({"roles": ["Mail.Send", 7]}),
            "markup in a role": jwt({"roles": ["<script>"]}),
            "too many roles": jwt({"roles": [f"Role{index}" for index in range(65)]}),
        }
        for label, token in cases.items():
            with self.subTest(label):
                self.assertIsNone(token_roles(token))

    @override_settings(GRAPH_APPROVED_APPLICATION_ROLES=("Mail.Send", "Mail.Read", "Mail.Send"))
    def test_the_approval_comes_from_settings(self):
        self.assertEqual(approved_roles(), APPROVED)


class RolesResultTests(SimpleTestCase):
    def test_roles_within_the_approval_pass(self):
        result = roles_result(APPROVED, APPROVED, "")

        self.assertEqual((result.check, result.outcome), ("roles", PASS))
        self.assertEqual(result.note, "granted Mail.Read, Mail.Send")

    def test_mail_readwrite_beyond_the_approval_fails(self):
        # What OIT reportedly configured; before this check existed the run printed a success line for it.
        result = roles_result(OIT_ROLES, APPROVED, "")

        self.assertEqual(result.outcome, FAIL)
        self.assertIn("beyond the approval: Mail.ReadWrite", result.note)
        self.assertIn("needs OIT to remove them or an InfoSec review", result.note)

    def test_an_infosec_exception_turns_the_failure_into_a_warning_that_names_it(self):
        result = roles_result(OIT_ROLES, APPROVED, "RITM0450999")

        self.assertEqual(result.outcome, WARN)
        self.assertIn("beyond the approval: Mail.ReadWrite; InfoSec exception RITM0450999", result.note)

    def test_no_roles_warn_that_rbac_grants_are_invisible(self):
        result = roles_result((), APPROVED, "")

        self.assertEqual(result.outcome, WARN)
        self.assertIn("RBAC for Applications grants never appear there", result.note)

    def test_unreadable_roles_are_inconclusive(self):
        result = roles_result(None, APPROVED, "RITM0450999")

        self.assertEqual(result.outcome, INCONCLUSIVE)
        self.assertEqual(result.expected, "within Mail.Read, Mail.Send")
