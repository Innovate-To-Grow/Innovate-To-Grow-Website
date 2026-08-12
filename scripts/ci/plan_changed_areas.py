#!/usr/bin/env python3
"""Plan CI areas from changed files."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChangedAreasPlan:
    backend: bool
    frontend: bool
    archive: bool

    def github_outputs(self) -> str:
        return "\n".join(
            [
                f"backend={str(self.backend).lower()}",
                f"frontend={str(self.frontend).lower()}",
                f"archive={str(self.archive).lower()}",
            ]
        )


def _normalize_files(files: Iterable[str]) -> list[str]:
    normalized = []
    for file_name in files:
        clean = file_name.strip()
        if clean:
            normalized.append(clean)
    return normalized


def _is_backend_path(path: str) -> bool:
    if path.startswith(("src/", "aws/", "scripts/", ".github/")):
        return True
    return path in {
        "pyproject.toml",
        ".pre-commit-config.yaml",
        ".bandit-baseline.json",
    }


def plan_changed_areas(event_name: str, changed_files: Iterable[str]) -> ChangedAreasPlan:
    files = _normalize_files(changed_files)

    if event_name != "pull_request":
        return ChangedAreasPlan(backend=True, frontend=True, archive=True)

    return ChangedAreasPlan(
        backend=any(_is_backend_path(path) for path in files),
        frontend=any(path.startswith(("pages/", ".github/")) for path in files),
        archive=any(path.startswith("archive/") for path in files),
    )


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

    plan = plan_changed_areas(
        event_name=args.event_name,
        changed_files=_read_changed_files(args.changed_files, args.files),
    )
    print(plan.github_outputs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
