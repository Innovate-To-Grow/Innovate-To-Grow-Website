#!/usr/bin/env python3
"""Enforce independent line and branch coverage floors for coverage.py JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _percentage(covered: int, total: int) -> float:
    if covered < 0 or total < 0 or covered > total:
        raise ValueError("coverage counts must satisfy 0 <= covered <= total")
    return 100.0 if total == 0 else 100 * covered / total


def check_coverage(report: dict[str, Any], line_floor: float, branch_floor: float) -> tuple[float, float]:
    try:
        totals = report["totals"]
        line_percent = _percentage(totals["covered_lines"], totals["num_statements"])
        branch_percent = _percentage(totals["covered_branches"], totals["num_branches"])
    except (KeyError, TypeError) as exc:
        raise ValueError("coverage report is missing required totals") from exc

    failures = []
    if line_percent < line_floor:
        failures.append(f"line coverage {line_percent:.2f}% is below {line_floor:.2f}%")
    if branch_percent < branch_floor:
        failures.append(f"branch coverage {branch_percent:.2f}% is below {branch_floor:.2f}%")
    if failures:
        raise ValueError("; ".join(failures))
    return line_percent, branch_percent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--line-floor", type=float, required=True)
    parser.add_argument("--branch-floor", type=float, required=True)
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        line_percent, branch_percent = check_coverage(report, args.line_floor, args.branch_floor)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Coverage check failed: {exc}", file=sys.stderr)
        return 1

    print(f"Line coverage: {line_percent:.2f}% (floor {args.line_floor:.2f}%)")
    print(f"Branch coverage: {branch_percent:.2f}% (floor {args.branch_floor:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
