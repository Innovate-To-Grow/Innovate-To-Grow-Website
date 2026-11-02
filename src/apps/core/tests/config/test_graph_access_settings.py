"""Microsoft Graph access-check settings per environment, and the system check that validates them at startup."""

from unittest.mock import patch

from django.conf import settings
from django.core.checks import registry
from django.test import SimpleTestCase, override_settings

from apps.core.checks import check_credential_store, check_microsoft_graph
from config.settings.base.integrations import microsoft_graph as base_settings
from config.settings.environments import test as ci_settings

from .test_prod_cache import PROD_ENV, reload_prod_settings


def error_ids():
    return [error.id for error in check_microsoft_graph() + check_credential_store()]


class GraphAccessSettingsTests(SimpleTestCase):
    def test_the_approval_and_the_gate_default_off_outside_production(self):
        self.assertEqual(base_settings.GRAPH_APPROVED_APPLICATION_ROLES, ("Mail.Send", "Mail.Read"))
        self.assertEqual(base_settings.GRAPH_ACCEPTED_BROADER_APPLICATION_ROLES, {"Mail.ReadWrite": ("Mail.Read",)})
        self.assertFalse(base_settings.GRAPH_REQUIRE_ACCESS_EVIDENCE)
        self.assertFalse(getattr(ci_settings, "GRAPH_REQUIRE_ACCESS_EVIDENCE", False))
        self.assertFalse(settings.GRAPH_REQUIRE_ACCESS_EVIDENCE)

    def test_production_turns_the_go_live_gate_on_and_passes_its_own_check(self):
        with patch.dict("os.environ", PROD_ENV, clear=True):
            production = reload_prod_settings()

        self.assertIs(production.GRAPH_REQUIRE_ACCESS_EVIDENCE, True)
        self.assertEqual(production.GRAPH_APPROVED_APPLICATION_ROLES, ("Mail.Send", "Mail.Read"))
        self.assertEqual(production.GRAPH_ACCEPTED_BROADER_APPLICATION_ROLES, {"Mail.ReadWrite": ("Mail.Read",)})
        values = {name: getattr(production, name) for name in dir(production) if name.startswith("GRAPH_")}
        with override_settings(**values):
            self.assertEqual(error_ids(), [])

    def test_the_limits_are_positive_numbers(self):
        for name in (
            "GRAPH_ACCESS_CHECK_TIMEOUT_SECONDS",
            "GRAPH_ACCESS_CHECK_MIME_MAX_BYTES",
            "GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS",
        ):
            with self.subTest(name=name):
                self.assertGreater(getattr(base_settings, name), 0)
                for bad in (0, -1, "10", None):
                    with override_settings(**{name: bad}):
                        self.assertIn("core.E005", error_ids())


class GraphAccessCheckTests(SimpleTestCase):
    def test_check_is_registered_and_the_test_settings_pass(self):
        self.assertIn(check_microsoft_graph, registry.registry.get_checks())
        self.assertEqual(error_ids(), [])

    def test_the_approval_must_list_graph_permission_names(self):
        for bad in ((), [], "Mail.Send", ("Mail.Send", ""), ("Mail.Send", "Mail Send"), ("Mail.Send", 7), None):
            with self.subTest(value=bad), override_settings(GRAPH_APPROVED_APPLICATION_ROLES=bad):
                self.assertEqual(error_ids(), ["core.E006"])
        with override_settings(GRAPH_APPROVED_APPLICATION_ROLES=["Mail.Send"]):
            self.assertEqual(error_ids(), [])

    def test_the_accepted_broader_roles_must_map_permission_names_to_what_they_cover(self):
        bad_values = (
            None,
            ("Mail.ReadWrite",),
            {"Mail ReadWrite": ("Mail.Read",)},
            {"Mail.ReadWrite": "Mail.Read"},
            {"Mail.ReadWrite": ()},
            {"Mail.ReadWrite": ("Mail.Read", 7)},
            {7: ("Mail.Read",)},
        )
        for bad in bad_values:
            with self.subTest(value=bad), override_settings(GRAPH_ACCEPTED_BROADER_APPLICATION_ROLES=bad):
                self.assertEqual(error_ids(), ["core.E013"])
        for good in ({}, {"Mail.ReadWrite": ["Mail.Read"]}):
            with override_settings(GRAPH_ACCEPTED_BROADER_APPLICATION_ROLES=good):
                self.assertEqual(error_ids(), [])

    def test_the_gate_flag_must_be_a_boolean(self):
        for bad in ("True", 1, None):
            with self.subTest(value=bad), override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=bad):
                self.assertEqual(error_ids(), ["core.E007"])
