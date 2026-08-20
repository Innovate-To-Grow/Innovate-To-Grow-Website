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
    cli: bool
    archive: bool
    status: bool

    def github_outputs(self) -> str:
        return "\n".join(
            [
                f"backend={str(self.backend).lower()}",
                f"frontend={str(self.frontend).lower()}",
                f"cli={str(self.cli).lower()}",
                f"archive={str(self.archive).lower()}",
                f"status={str(self.status).lower()}",
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


def _is_ci_relevant_path(path: str) -> bool:
    """True when `path` is an area a push to main validates.

    Mirrors `on.push.paths` in .github/workflows/ci.yml. `.github/` is matched a
    little more broadly than that list (which names only `.github/dependabot.yml`
    and `.github/workflows/**`); erring toward running is the safe direction.
    """
    return _is_backend_path(path) or path.startswith(("pages/", "cli/", "archive/", "status/"))


FULL_SUITE = ChangedAreasPlan(backend=True, frontend=True, cli=True, archive=True, status=True)
NO_SUITE = ChangedAreasPlan(backend=False, frontend=False, cli=False, archive=False, status=False)


def plan_changed_areas(event_name: str, changed_files: Iterable[str]) -> ChangedAreasPlan:
    """Return the areas CI must validate.

    PR/push parity: a pull request runs the SAME areas a push to main runs
    whenever it touches any path in `on.push.paths`, so a green PR check cannot
    become a red main run for the same tree. Branch protection sets
    `strict: true` and `pull_request` checks out `refs/pull/N/merge`, so the PR
    already tests the merge-result tree; before this rule it additionally ran a
    diff-scoped SUBSET of the jobs, which is what let backend-only PR #433 merge
    without ever running the E2E matrix. The post-merge run 32107167026 then
    failed the iphone14 + ipad legs (though it still reported `CI Result` green,
    because `e2e` was `continue-on-error` at the time — see `e2e-required-result`
    in ci.yml for the other half of the fix).

    PRs that touch only PR-only paths still run nothing: `.claude/**` is in
    `on.pull_request.paths` but deliberately NOT in `on.push.paths`, so merging
    one starts no CI run and there is nothing to diverge from. `ci-result` is
    `if: always()`, so the required `CI Result` check is still reported.
    """
    files = _normalize_files(changed_files)

    if event_name != "pull_request":
        # A push to main/master always validates every area: it is the run the
        # deploy-*.yml chain consumes, and `backend-image-publish` must run so
        # deploy-backend.yml can pull `itg-backend:<sha>`.
        return FULL_SUITE

    if any(_is_ci_relevant_path(path) for path in files):
        return FULL_SUITE
    return NO_SUITE


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
