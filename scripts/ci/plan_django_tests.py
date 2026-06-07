#!/usr/bin/env python3
"""Plan the Django app test matrix from changed files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ALL_APPS = [
    "authn",
    "core",
    "common",
    "system_intelligence",
    "cms",
    "event",
    "projects",
    "mail",
    "cli_admin",
]

APP_LOCAL_RE = re.compile(
    r"^src/apps/"
    r"(?P<app>authn|system_intelligence|cms|event|projects|mail|cli_admin)/"
)


def _normalize_files(files: Iterable[str]) -> list[str]:
    normalized = []
    for file_name in files:
        clean = file_name.strip()
        if clean:
            normalized.append(clean)
    return normalized


def _is_shared_backend_file(path: str) -> bool:
    if path.startswith((".github/", "aws/", "scripts/")):
        return True
    if path in {
        "pyproject.toml",
        ".pre-commit-config.yaml",
        ".bandit-baseline.json",
        "src/Dockerfile",
        "src/entrypoint.sh",
        "src/manage.py",
        "src/requirements.txt",
    }:
        return True
    return path.startswith(
        (
            "src/config/",
            "src/requirements/",
            "src/apps/core/",
            "src/apps/common/",
        )
    )


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
    files = _normalize_files(changed_files)

    if event_name != "pull_request":
        return DjangoPlan(ALL_APPS.copy(), True)

    if not files:
        return DjangoPlan(ALL_APPS.copy(), True)

    if any(_is_shared_backend_file(path) for path in files):
        return DjangoPlan(ALL_APPS.copy(), True)

    changed_apps = {
        match.group("app")
        for path in files
        if (match := APP_LOCAL_RE.match(path)) is not None
    }

    if not changed_apps:
        return DjangoPlan(ALL_APPS.copy(), True)

    apps = [app for app in ALL_APPS if app in changed_apps]
    return DjangoPlan(apps, "cli_admin" in changed_apps)


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
