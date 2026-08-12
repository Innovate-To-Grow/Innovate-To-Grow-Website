#!/usr/bin/env python3
"""Enforce independent per-app line and branch floors from coverage.py JSON."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """The coverage report or floor configuration is invalid."""


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigurationError(f"{label} must be a finite number")
    number = float(value)
    if not 0 <= number <= 100:
        raise ConfigurationError(f"{label} must be between 0 and 100 inclusive")
    return number


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"{label} file not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read {label} file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a JSON object")
    return value


def parse_floors(config: dict[str, Any]) -> dict[str, tuple[float, float]]:
    apps = config.get("apps")
    if not isinstance(apps, dict) or not apps:
        raise ConfigurationError("configuration must contain a non-empty 'apps' object")
    parsed = {}
    for app, floors in apps.items():
        if not isinstance(app, str) or not app or "/" in app or "\\" in app:
            raise ConfigurationError(f"invalid app name: {app!r}")
        if not isinstance(floors, dict):
            raise ConfigurationError(f"floor for app {app!r} must be an object")
        unknown = set(floors) - {"line", "branch"}
        missing = {"line", "branch"} - set(floors)
        if unknown or missing:
            details = []
            if missing:
                details.append(f"missing {', '.join(sorted(missing))}")
            if unknown:
                details.append(f"unknown {', '.join(sorted(unknown))}")
            raise ConfigurationError(f"invalid floor for app {app!r}: {'; '.join(details)}")
        parsed[app] = (_number(floors["line"], f"{app}.line"), _number(floors["branch"], f"{app}.branch"))
    return parsed


def _count(summary: dict[str, Any], key: str, filename: str) -> int:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"coverage summary for {filename!r} has invalid {key!r}")
    return value


def check_coverage(report: dict[str, Any], floors: dict[str, tuple[float, float]]) -> list[str]:
    files = report.get("files")
    if not isinstance(files, dict):
        raise ConfigurationError("coverage report must contain a 'files' object")
    failures = []
    for app, (line_floor, branch_floor) in floors.items():
        prefixes = (f"apps/{app}/", f"src/apps/{app}/")
        matched = [
            (name.replace("\\", "/"), data)
            for name, data in files.items()
            if name.replace("\\", "/").startswith(prefixes)
        ]
        if not matched:
            failures.append(f"{app}: no coverage files found under apps/{app}/")
            continue
        totals = dict.fromkeys(("covered_lines", "num_statements", "covered_branches", "num_branches"), 0)
        for filename, data in matched:
            if not isinstance(data, dict) or not isinstance(data.get("summary"), dict):
                raise ConfigurationError(f"coverage entry for {filename!r} must contain a summary object")
            for key in totals:
                totals[key] += _count(data["summary"], key, filename)
        statements = totals["num_statements"]
        branches = totals["num_branches"]
        if statements == 0:
            failures.append(f"{app}: no executable lines (line floor {line_floor:.2f}%)")
        else:
            actual = totals["covered_lines"] * 100 / statements
            if actual + 1e-12 < line_floor:
                failures.append(
                    f"{app}: line {actual:.2f}% is below {line_floor:.2f}% ({totals['covered_lines']}/{statements})"
                )
        if branches == 0:
            failures.append(f"{app}: zero branches; cannot enforce branch floor {branch_floor:.2f}%")
        else:
            actual = totals["covered_branches"] * 100 / branches
            if actual + 1e-12 < branch_floor:
                failures.append(
                    f"{app}: branch {actual:.2f}% is below {branch_floor:.2f}% ({totals['covered_branches']}/{branches})"
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("floors_json", type=Path)
    parser.add_argument("--app", help="Check only one configured app (for matrix jobs).")
    args = parser.parse_args(argv)
    try:
        report = load_json(args.coverage_json, "coverage")
        floors = parse_floors(load_json(args.floors_json, "floor configuration"))
        if args.app:
            if args.app not in floors:
                raise ConfigurationError(f"app {args.app!r} is not configured")
            floors = {args.app: floors[args.app]}
        failures = check_coverage(report, floors)
    except ConfigurationError as exc:
        print(f"backend coverage check error: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("Backend coverage floors failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Backend coverage floors passed for {len(floors)} app(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
