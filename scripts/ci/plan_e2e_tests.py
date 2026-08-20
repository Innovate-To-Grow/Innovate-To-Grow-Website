#!/usr/bin/env python3
"""Plan Playwright projects and specs from changed files."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

FULL_PROJECTS = [
    "chromium",
    "firefox",
    "webkit",
    "pixel7",
    "iphone14",
    "iphone-se",
    "ipad",
    # Current flagships + newest Android tablet — keep in sync with pages/playwright.config.ts.
    "iphone-17-pro-max",
    "galaxy-s26-ultra",
    "galaxy-tab-s9",
]


@dataclass(frozen=True)
class E2ELeg:
    project: str
    spec_args: str


@dataclass(frozen=True)
class E2EPlan:
    projects: list[str]
    specs: list[str]
    matrix: list[E2ELeg]

    @property
    def spec_args(self) -> str:
        return " ".join(shlex.quote(spec) for spec in self.specs)

    def github_outputs(self) -> str:
        matrix = [{"project": leg.project, "spec_args": leg.spec_args} for leg in self.matrix]
        return "\n".join(
            [
                f"projects={json.dumps(self.projects, separators=(',', ':'))}",
                f"specs={json.dumps(self.specs, separators=(',', ':'))}",
                f"spec_args={self.spec_args}",
                f"matrix={json.dumps(matrix, separators=(',', ':'))}",
            ]
        )


def _full_plan(projects: list[str]) -> E2EPlan:
    return E2EPlan(
        projects=projects,
        specs=[],
        matrix=[E2ELeg(project=project, spec_args="") for project in projects],
    )


def plan_e2e_tests(event_name: str, changed_files: Iterable[str]) -> E2EPlan:
    """Return the full device matrix with no spec filter, for every event.

    Pull requests used to run only `chromium` with a diff-derived spec subset.
    That structurally hid device-specific failures: PR #433 was green (E2E
    skipped outright) and the post-merge run 32107167026 failed on `iphone14`
    and `ipad` at pages/e2e/events/subscribe.spec.ts:94 while `chromium` passed.
    PR and push now run an identical matrix. `event_name` / `changed_files` are
    accepted and ignored so the CLI and the ci.yml call site stay unchanged.
    """
    return _full_plan(FULL_PROJECTS.copy())


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

    plan = plan_e2e_tests(
        event_name=args.event_name,
        changed_files=_read_changed_files(args.changed_files, args.files),
    )
    print(plan.github_outputs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
