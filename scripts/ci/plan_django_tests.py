#!/usr/bin/env python3
"""Plan the Django app test matrix from changed files."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ALL_APPS = [
    "authn",
    "core",
    "system_intelligence",
    "cms",
    "event",
    "projects",
    "mail",
    "cli_admin",
]


@dataclass(frozen=True)
class DjangoPlan:
    apps: list[str]
    cli_admin_coverage: bool

    def github_outputs(self) -> str:
        return "\n".join(
            [
                f"apps={json.dumps(self.apps, separators=(',', ':'))}",
                f"cli_admin_coverage={str(self.cli_admin_coverage).lower()}",
            ]
        )


def plan_django_tests(event_name: str, changed_files: Iterable[str]) -> DjangoPlan:
    """Run every app suite plus the cli_admin/safe_orm coverage gate, always.

    PR-only app scoping meant a PR confined to one app never ran the other seven
    suites and set `cli_admin_coverage=false`, so the 100%-coverage gate on
    apps.cli_admin + the shared safe_orm service (`CLI Admin Coverage`) was
    skipped on the PR and enforced for the first time on main. `event_name` /
    `changed_files` are accepted and ignored so the CLI and the ci.yml call site
    stay unchanged.
    """
    return DjangoPlan(ALL_APPS.copy(), True)


def _read_changed_files(path: str | None, positional_files: list[str]) -> list[str]:
    files = list(positional_files)
    if path:
        files.extend(Path(path).read_text(encoding="utf-8").splitlines())
    if not path and not positional_files and not sys.stdin.isatty():
        files.extend(sys.stdin.read().splitlines())
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--changed-files", help="Newline-delimited changed-files path.")
    parser.add_argument("files", nargs="*", help="Changed files, when not using stdin.")
    args = parser.parse_args(argv)

    plan = plan_django_tests(
        event_name=args.event_name,
        changed_files=_read_changed_files(args.changed_files, args.files),
    )
    print(plan.github_outputs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
