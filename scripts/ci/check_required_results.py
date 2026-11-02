#!/usr/bin/env python3
"""Fail a roll-up job when one of the jobs it needs did not pass.

Reads the job's `needs` context as JSON from the NEEDS_CONTEXT environment
variable (`${{ toJson(needs) }}`). A need passes when its result is `success`,
or `skipped` unless --skipped-is-failure is given: a roll-up whose needs can
never be legitimately skipped (the E2E matrix, the frontend checks) must not
pass a run in which they never ran.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping


def failures(
    needs: Mapping[str, Mapping[str, object]], *, ignore: Iterable[str] = (), skipped_ok: bool = True
) -> dict[str, str]:
    """The needs that did not pass, as {job id: result}, in `needs` order."""
    passing = {"success", "skipped"} if skipped_ok else {"success"}
    ignored = set(ignore)
    return {
        name: str(data.get("result"))
        for name, data in needs.items()
        if name not in ignored and data.get("result") not in passing
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ignore", action="append", default=[], metavar="JOB", help="a need to leave out (repeatable)")
    parser.add_argument("--skipped-is-failure", action="store_true", help="treat a skipped need as a failure")
    parser.add_argument("--passed-message", default="All required checks passed.", help="printed when all pass")
    args = parser.parse_args(argv)

    needs = json.loads(os.environ["NEEDS_CONTEXT"])
    failed = failures(needs, ignore=args.ignore, skipped_ok=not args.skipped_is_failure)
    if failed:
        for name, result in failed.items():
            detail = " (an upstream failure cascaded; it never ran)" if result == "skipped" else ""
            print(f"{name}: {result}{detail}")
        return 1
    print(args.passed_message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
