"""Workflows select tests by app, tag or discovery, never by a test module's path.

A refactor that moves or splits a test module must not be able to break CI silently: a hardcoded
`apps.core.tests.services.test_safe_orm` label once failed the cli_admin job with ModuleNotFoundError on
every PR built on the move. The safe_orm gate now runs the classes tagged "safe_orm", and the required
smoke run selects the spec by its @required-smoke tag.
"""

from __future__ import annotations

import re
import unittest

from scripts.ci.tests.workflow.ci_workflow import WORKFLOW_DIRECTORY, load_yaml, steps_of

DJANGO_TEST_MODULE = re.compile(r"\bapps\.[a-z_]+\.tests\.[a-z_][\w.]*")
PLAYWRIGHT_SPEC_PATH = re.compile(r"\bplaywright test\b[^\n]*?[\w./-]+\.spec\.ts")


def run_steps():
    for path in sorted(WORKFLOW_DIRECTORY.glob("*.yml")):
        for job_name, job in (load_yaml(path).get("jobs") or {}).items():
            for step in steps_of(job):
                if "run" in step:
                    yield f"{path.name} / {job_name} / {step.get('name', '?')}", step["run"]


class WorkflowTestSelectionTests(unittest.TestCase):
    def test_no_step_names_a_django_test_module(self):
        offenders = [where for where, script in run_steps() if DJANGO_TEST_MODULE.search(script)]
        self.assertEqual(offenders, [], "select Django tests by app label or @tag, not by a test module path")

    def test_no_step_names_a_playwright_spec_file(self):
        offenders = [where for where, script in run_steps() if PLAYWRIGHT_SPEC_PATH.search(script)]
        self.assertEqual(offenders, [], "select Playwright tests by project or --grep @tag, not by a spec path")

    def test_the_safe_orm_gate_runs_the_tagged_tests(self):
        scripts = [script for _, script in run_steps() if "coverage-cli-admin-safe-orm.json" in script]
        self.assertEqual(len(scripts), 1)
        self.assertIn("manage.py test apps --tag safe_orm", scripts[0])
        self.assertIn("--fail-under=100", scripts[0])


if __name__ == "__main__":
    unittest.main()
