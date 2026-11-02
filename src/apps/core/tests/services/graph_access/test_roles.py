"""The access token's ``roles`` claim: read without trusting it, and judged against the approval."""

from django.test import SimpleTestCase, override_settings

from apps.core.services.email.graph.access_check import FAIL, INCONCLUSIVE, PASS, WARN
from apps.core.services.email.graph.access_check.roles import approved_roles, roles_result, token_roles
from apps.core.tests.services.graph_access.helpers import (
    APPROVED,
    EXTRA_ROLES,
    NARROW_ROLES,
    OIT_ROLES,
    jwt,
    token_with_roles,
)


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

    def test_the_most_roles_read_is_a_setting(self):
        token = jwt({"roles": ["Mail.Read", "Mail.Send"]})

        with override_settings(GRAPH_ACCESS_CHECK_MAX_ROLES=1):
            self.assertIsNone(token_roles(token))
        self.assertEqual(token_roles(token), ("Mail.Read", "Mail.Send"))

    def test_the_approved_roles_are_what_oit_granted(self):
        self.assertEqual(approved_roles(), APPROVED)

    @override_settings(GRAPH_APPROVED_APPLICATION_ROLES=("Mail.Send", "Mail.Read", "Mail.Send"))
    def test_the_approval_comes_from_settings(self):
        self.assertEqual(approved_roles(), NARROW_ROLES)


class RolesResultTests(SimpleTestCase):
    def test_what_oit_granted_passes_cleanly(self):
        result = roles_result(OIT_ROLES, APPROVED, "")

        self.assertEqual((result.check, result.outcome), ("roles", PASS))
        self.assertEqual(result.note, "granted Mail.ReadWrite, Mail.Send")

    def test_a_narrower_grant_also_passes(self):
        result = roles_result(NARROW_ROLES, APPROVED, "")

        self.assertEqual((result.outcome, result.note), (PASS, "granted Mail.Read, Mail.Send"))

    def test_a_role_beyond_the_approved_ones_fails(self):
        result = roles_result(EXTRA_ROLES, APPROVED, "")

        self.assertEqual(result.outcome, FAIL)
        self.assertIn("beyond the approval: User.Read.All", result.note)
        self.assertIn("needs OIT to remove them or an InfoSec review", result.note)

    def test_an_infosec_exception_turns_the_failure_into_a_warning_that_names_it(self):
        result = roles_result(EXTRA_ROLES, APPROVED, "RITM0450999")

        self.assertEqual(result.outcome, WARN)
        self.assertIn("beyond the approval: User.Read.All; InfoSec exception RITM0450999", result.note)

    def test_no_roles_warn_that_rbac_grants_are_invisible(self):
        result = roles_result((), APPROVED, "")

        self.assertEqual(result.outcome, WARN)
        self.assertIn("RBAC for Applications grants never appear there", result.note)

    def test_unreadable_roles_are_inconclusive(self):
        result = roles_result(None, APPROVED, "RITM0450999")

        self.assertEqual(result.outcome, INCONCLUSIVE)
        self.assertEqual(result.expected, "within Mail.Read, Mail.ReadWrite, Mail.Send")
