from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from scripts.ci.check_required_results import failures, main


def needs(**results: str) -> dict[str, dict[str, object]]:
    return {name.replace("_", "-"): {"result": result, "outputs": {}} for name, result in results.items()}


class FailuresTests(unittest.TestCase):
    def test_success_and_skipped_pass_by_default(self) -> None:
        self.assertEqual(failures(needs(lint="success", e2e="skipped")), {})

    def test_failed_and_cancelled_needs_are_reported_in_order(self) -> None:
        result = failures(needs(lint="failure", build="success", e2e="cancelled"))

        self.assertEqual(list(result.items()), [("lint", "failure"), ("e2e", "cancelled")])

    def test_skipped_is_a_failure_when_requested(self) -> None:
        # The E2E gate: a matrix that never ran must not pass (PR #439).
        self.assertEqual(failures(needs(e2e="skipped"), skipped_ok=False), {"e2e": "skipped"})
        self.assertEqual(failures(needs(e2e="success"), skipped_ok=False), {})

    def test_ignored_needs_are_left_out(self) -> None:
        self.assertEqual(failures(needs(changes="failure", lint="success"), ignore=["changes"]), {})

    def test_a_need_is_only_ignored_when_named(self) -> None:
        # ci-result checks `changes` and `preflight` itself.
        self.assertEqual(failures(needs(changes="failure", preflight="success")), {"changes": "failure"})

    def test_a_missing_result_is_a_failure(self) -> None:
        self.assertEqual(failures({"lint": {}}), {"lint": "None"})


class MainTests(unittest.TestCase):
    def run_main(self, context: dict[str, dict[str, object]], *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"NEEDS_CONTEXT": json.dumps(context)}), redirect_stdout(output):
            status = main(list(argv))
        return status, output.getvalue()

    def test_all_passing_prints_the_message_and_exits_zero(self) -> None:
        status, output = self.run_main(needs(lint="success"), "--passed-message", "All backend checks passed.")

        self.assertEqual((status, output), (0, "All backend checks passed.\n"))

    def test_a_failure_is_printed_and_exits_one(self) -> None:
        status, output = self.run_main(needs(changes="success", lint="failure"), "--ignore", "changes")

        self.assertEqual((status, output), (1, "lint: failure\n"))

    def test_skipped_is_failure_flag(self) -> None:
        status, output = self.run_main(
            needs(changes="success", e2e="skipped"), "--ignore", "changes", "--skipped-is-failure"
        )

        self.assertEqual((status, output), (1, "e2e: skipped (an upstream failure cascaded; it never ran)\n"))


if __name__ == "__main__":
    unittest.main()
