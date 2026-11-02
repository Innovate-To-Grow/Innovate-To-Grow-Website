"""The access token's ``roles`` claim: read without trusting it, and judged against the approval."""

from django.test import SimpleTestCase, override_settings

from apps.core.services.email.graph.access_check import FAIL, INCONCLUSIVE, PASS, WARN
from apps.core.services.email.graph.access_check.roles import (
    accepted_broader_roles,
    approved_roles,
    roles_result,
    token_roles,
)
from apps.core.tests.services.graph_access.helpers import APPROVED, OIT_ROLES, UNACCEPTED_ROLES, jwt, token_with_roles

BROADER = ("Mail.ReadWrite",)


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

    @override_settings(GRAPH_APPROVED_APPLICATION_ROLES=("Mail.Send", "Mail.Read", "Mail.Send"))
    def test_the_approval_comes_from_settings(self):
        self.assertEqual(approved_roles(), APPROVED)


class RolesResultTests(SimpleTestCase):
    def test_roles_within_the_approval_pass(self):
        result = roles_result(APPROVED, APPROVED, "")

        self.assertEqual((result.check, result.outcome), ("roles", PASS))
        self.assertEqual(result.note, "granted Mail.Read, Mail.Send")

    def test_mail_readwrite_as_oit_granted_it_is_accepted_without_an_exception(self):
        result = roles_result(OIT_ROLES, APPROVED, "", BROADER)

        self.assertEqual(result.outcome, WARN)
        self.assertEqual(
            result.note,
            "granted Mail.ReadWrite, Mail.Send; beyond the approval: Mail.ReadWrite; accepted as granted, covering an "
            "approved role: Mail.ReadWrite",
        )

    def test_a_role_that_is_not_an_accepted_broader_grant_fails(self):
        for granted in (UNACCEPTED_ROLES, (*OIT_ROLES, "User.Read.All")):
            with self.subTest(granted=granted):
                result = roles_result(granted, APPROVED, "", BROADER)

                self.assertEqual(result.outcome, FAIL)
                self.assertIn("User.Read.All", result.note)
                self.assertIn("needs OIT to remove them or an InfoSec review", result.note)
        # Without the accepted broader roles (as before), Mail.ReadWrite fails too.
        self.assertEqual(roles_result(OIT_ROLES, APPROVED, "").outcome, FAIL)

    def test_an_infosec_exception_turns_the_failure_into_a_warning_that_names_it(self):
        result = roles_result(UNACCEPTED_ROLES, APPROVED, "RITM0450999", BROADER)

        self.assertEqual(result.outcome, WARN)
        self.assertIn("beyond the approval: User.Read.All; InfoSec exception RITM0450999", result.note)

    def test_no_roles_warn_that_rbac_grants_are_invisible(self):
        result = roles_result((), APPROVED, "")

        self.assertEqual(result.outcome, WARN)
        self.assertIn("RBAC for Applications grants never appear there", result.note)

    def test_unreadable_roles_are_inconclusive(self):
        result = roles_result(None, APPROVED, "RITM0450999")

        self.assertEqual(result.outcome, INCONCLUSIVE)
        self.assertEqual(result.expected, "within Mail.Read, Mail.Send")


class AcceptedBroaderRolesTests(SimpleTestCase):
    def test_mail_readwrite_is_accepted_by_default(self):
        self.assertEqual(accepted_broader_roles(), BROADER)

    @override_settings(GRAPH_APPROVED_APPLICATION_ROLES=("Mail.Send",))
    def test_a_broader_role_is_withdrawn_when_a_role_it_covers_is_no_longer_approved(self):
        self.assertEqual(accepted_broader_roles(), ())

    def test_only_entries_that_cover_approved_roles_and_are_not_approved_themselves_count(self):
        mapping = {
            "Mail.ReadWrite": ("Mail.Read",),
            "Mail.ReadBasic.All": (),
            "Calendars.ReadWrite": ("Calendars.Read",),
            "Mail.Send": ("Mail.Send",),
        }
        with override_settings(GRAPH_ACCEPTED_BROADER_APPLICATION_ROLES=mapping):
            self.assertEqual(accepted_broader_roles(), ("Mail.ReadWrite",))
        with override_settings(GRAPH_ACCEPTED_BROADER_APPLICATION_ROLES={}):
            self.assertEqual(accepted_broader_roles(), ())
