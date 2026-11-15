#!/usr/bin/env python3
"""Keep tool and runtime version pins in sync across CI, deploy workflows and git hooks.

Each pin group lists every place one version is written down, and all of them must agree. A source that
finds fewer matches than it expects is an error rather than a silent skip, so a renamed key or a rewritten
line cannot quietly drop out of the check. (src/Dockerfile vs BACKEND_PYTHON_VERSION is guarded by
scripts/ci/tests/workflow/test_ci_workflow_invariants.py instead.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pins import collect_pins, mismatches
from .sources import ROOT, PinError


def _shorten(value: str, width: int = 60) -> str:
    return value if len(value) <= width else value[: width - 3] + "..."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that tool and runtime version pins agree.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository checkout to check (default: this one)")
    root = parser.parse_args(argv).root
    try:
        pins = collect_pins(root)
    except PinError as exc:
        print(f"Cannot check tool versions: {exc}", file=sys.stderr)
        return 1
    problems = mismatches(pins)
    if problems:
        print("Tool version pins disagree:", *problems, sep="\n  ", file=sys.stderr)
        return 1
    print("Tool versions aligned: " + ", ".join(f"{group}={_shorten(pins[group][0][1])}" for group in pins))
    return 0
