from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from scripts.ci import check_python_dependencies as deps
from scripts.ci.check_python_dependencies import (
    Import,
    boundary_violations,
    exception_matches,
    import_cycles,
    load_config,
    resolve_imports,
    strongly_connected,
)

CONFIG = {
    "composition": ["apps.core.management.commands.*"],
    "allowed": {"core": [], "authn": ["core"], "mail": ["core", "event.services.public"]},
}


def _import(source: str, target: str, top_level: bool = True) -> Import:
    return Import(source=source, target=target, line=1, top_level=top_level)


class BoundaryTests(unittest.TestCase):
    def test_same_app_and_allowed_apps_pass(self) -> None:
        imports = [_import("apps.authn.views", "apps.authn.models"), _import("apps.authn.views", "apps.core.models")]
        self.assertEqual(boundary_violations(imports, CONFIG), [])

    def test_disallowed_direction_is_a_violation(self) -> None:
        backwards = _import("apps.core.utils", "apps.authn.models")
        self.assertEqual(boundary_violations([backwards], CONFIG), [backwards])

    def test_module_entries_allow_only_that_public_module(self) -> None:
        public = _import("apps.mail.views", "apps.event.services.public.tickets")
        private = _import("apps.mail.views", "apps.event.services.internal")
        lookalike = _import("apps.mail.views", "apps.event.services.public_extra")
        self.assertEqual(boundary_violations([public, private, lookalike], CONFIG), [private, lookalike])

    def test_composition_modules_may_import_any_app(self) -> None:
        command = _import("apps.core.management.commands.run_worker", "apps.mail.services")
        self.assertEqual(boundary_violations([command], CONFIG), [])

    def test_exceptions_match_the_target_module_and_its_submodules(self) -> None:
        entry = {"from": "apps.event.*", "to": "apps.mail.services.tokens"}
        self.assertTrue(exception_matches(_import("apps.event.views", "apps.mail.services.tokens.links"), entry))
        self.assertFalse(exception_matches(_import("apps.event.views", "apps.mail.services.tokenizer"), entry))
        self.assertFalse(exception_matches(_import("apps.cms.views", "apps.mail.services.tokens"), entry))

    def test_repository_config_entries_carry_reasons(self) -> None:
        config = load_config()
        for entry in [*config.get("exceptions", []), *config.get("cycles", [])]:
            with self.subTest(entry=entry):
                self.assertTrue(entry.get("reason", "").strip())


class ImportResolutionTests(unittest.TestCase):
    def test_type_checking_and_function_level_imports_are_not_top_level(self) -> None:
        source = textwrap.dedent(
            """\
            from typing import TYPE_CHECKING

            from apps.core.models import Base
            from . import helpers

            if TYPE_CHECKING:
                from apps.authn.models import Member

            def later():
                from apps.mail.services import send
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            path = src / "apps" / "event" / "views.py"
            path.parent.mkdir(parents=True)
            path.write_text(source, encoding="utf-8")
            known = {"apps.core.models", "apps.event.helpers", "apps.authn.models", "apps.mail.services"}
            with mock.patch.object(deps, "SRC", src):
                imports = resolve_imports("apps.event.views", path, known)
        by_target = {item.target: item.top_level for item in imports}
        self.assertEqual(
            by_target,
            {
                "apps.core.models": True,
                "apps.event.helpers": True,
                "apps.authn.models": False,
                "apps.mail.services": False,
            },
        )


class CycleTests(unittest.TestCase):
    def test_only_multi_module_components_are_reported(self) -> None:
        graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}, "e": set()}
        self.assertEqual(strongly_connected(graph), [["a", "b", "c"]])

    def test_function_level_imports_do_not_form_cycles(self) -> None:
        imports = [_import("apps.x.a", "apps.x.b"), _import("apps.x.b", "apps.x.a", top_level=False)]
        self.assertEqual(import_cycles(imports), [])

    def test_long_chains_do_not_hit_the_recursion_limit(self) -> None:
        size = 5000
        graph = {str(node): {str(node + 1)} for node in range(size)}
        graph[str(size)] = {"0"}
        (component,) = strongly_connected(graph)
        self.assertEqual(len(component), size + 1)


if __name__ == "__main__":
    unittest.main()
