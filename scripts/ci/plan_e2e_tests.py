#!/usr/bin/env python3
"""Plan Playwright projects and specs from changed files."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FULL_PROJECTS = [
    "chromium",
    "firefox",
    "webkit",
    "pixel7",
    "iphone14",
    "iphone-se",
    "ipad",
    # Android tablet + landscape variants — keep in sync with pages/playwright.config.ts.
    "galaxy-tab-s4",
    "pixel7-landscape",
    "iphone14-landscape",
]
PR_DEFAULT_PROJECTS = ["chromium"]

AUTH_SPECS = [
    "e2e/auth-login.spec.ts",
    "e2e/auth-password-reset.spec.ts",
    "e2e/auth-token-login.spec.ts",
    "e2e/account.spec.ts",
    "e2e/subscribe.spec.ts",
    "e2e/complete-profile.spec.ts",
    "e2e/cross-root-sync.spec.ts",
]
PROJECT_SPECS = ["e2e/projects.spec.ts"]
CONTENT_SPECS = [
    "e2e/content-archive.spec.ts",
    "e2e/news.spec.ts",
    "e2e/smoke.live.spec.ts",
    "e2e/cross-root-sync.spec.ts",
]
EVENT_SPECS = ["e2e/event-registration.spec.ts"]
MOBILE_SPECS = ["e2e/mobile.spec.ts"]
DESKTOP_MOBILE_COMPANION_SPECS = ["e2e/smoke.live.spec.ts"]

SPEC_TO_PATH_RE = re.compile(r"^pages/(e2e/[^/]+\.spec\.ts)$")


def _normalize_files(files: Iterable[str]) -> list[str]:
    normalized = []
    for file_name in files:
        clean = file_name.strip()
        if clean:
            normalized.append(clean)
    return normalized


def _matches_any(
    path: str,
    prefixes: Iterable[str] | str = (),
    patterns: Iterable[str] | str = (),
) -> bool:
    prefix_values = (prefixes,) if isinstance(prefixes, str) else tuple(prefixes)
    pattern_values = (patterns,) if isinstance(patterns, str) else tuple(patterns)
    return path.startswith(prefix_values) or any(re.search(pattern, path) for pattern in pattern_values)


def _is_global_path(path: str) -> bool:
    if path.startswith((".github/", "scripts/")):
        return True
    if path.startswith("pages/e2e/helpers/") or path == "pages/e2e/fixtures.ts":
        return True
    if path in {
        "pages/package.json",
        "pages/package-lock.json",
        "pages/playwright.config.ts",
        "pages/tsconfig.json",
        "pages/tsconfig.app.json",
        "pages/tsconfig.node.json",
        "pages/vite.config.ts",
        "pages/vitest.config.ts",
        "pages/src/main.tsx",
        "pages/src/App.tsx",
        "pages/src/index.css",
    }:
        return True
    return path.startswith(
        (
            "pages/src/app/",
            "pages/src/assets/styles/shared/",
            "pages/src/components/ui/",
            "pages/src/hooks/",
            "pages/src/lib/",
            "pages/src/types/",
        )
    )


def _is_mobile_path(path: str) -> bool:
    lowered = path.lower()
    return (
        path == "pages/e2e/mobile.spec.ts"
        or "mobile" in lowered
        or "responsive" in lowered
        or "menu" in lowered
        or "drawer" in lowered
    )


def _category_specs_for(path: str) -> set[str]:
    specs: set[str] = set()

    direct_spec = SPEC_TO_PATH_RE.match(path)
    if direct_spec and path != "pages/e2e/mobile.spec.ts":
        specs.add(direct_spec.group(1))

    if _matches_any(
        path,
        prefixes=("pages/src/features/auth/",),
        patterns=(
            r"^pages/src/routes/(MagicLoginPage|TicketLoginPage|UnsubscribeLoginPage|"
            r"ImpersonateLoginPage|EmailAuthLinkPage|SubscribePage)/",
            r"(^|/)(auth|account|subscribe|profile)[^/]*",
        ),
    ):
        specs.update(AUTH_SPECS)

    if _matches_any(
        path,
        prefixes=("pages/src/features/projects/",),
        patterns=r"^pages/src/routes/(ProjectsPage|PastProjectsPage|ProjectDetailPage|PresentingTeamsPage)/",
    ):
        specs.update(PROJECT_SPECS)

    if _matches_any(
        path,
        prefixes=("pages/src/features/cms/", "pages/src/features/news/", "pages/src/features/layout/"),
        patterns=(
            r"^pages/src/routes/(AcknowledgementPage|NewsPage|NewsDetailPage|SchedulePage)/",
            r"(^|/)(cms|news|content|layout)[^/]*",
        ),
    ):
        specs.update(CONTENT_SPECS)

    if _matches_any(
        path,
        prefixes=("pages/src/features/events/",),
        patterns=r"^pages/src/routes/(EventRegistrationPage|EventArchivePage)/",
    ):
        specs.update(EVENT_SPECS)

    return specs


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
        matrix = [
            {"project": leg.project, "spec_args": leg.spec_args}
            for leg in self.matrix
        ]
        return "\n".join(
            [
                f"projects={json.dumps(self.projects, separators=(',', ':'))}",
                f"specs={json.dumps(self.specs, separators=(',', ':'))}",
                f"spec_args={self.spec_args}",
                f"matrix={json.dumps(matrix, separators=(',', ':'))}",
            ]
        )


def _ordered_specs(specs: set[str]) -> list[str]:
    order = AUTH_SPECS + PROJECT_SPECS + CONTENT_SPECS + EVENT_SPECS + MOBILE_SPECS
    return [spec for spec in dict.fromkeys(order) if spec in specs]


def _full_plan(projects: list[str]) -> E2EPlan:
    return E2EPlan(
        projects=projects,
        specs=[],
        matrix=[E2ELeg(project=project, spec_args="") for project in projects],
    )


def plan_e2e_tests(event_name: str, changed_files: Iterable[str]) -> E2EPlan:
    files = _normalize_files(changed_files)

    if event_name != "pull_request":
        return _full_plan(FULL_PROJECTS.copy())

    if not files:
        return _full_plan(PR_DEFAULT_PROJECTS.copy())

    mobile_related = any(_is_mobile_path(path) for path in files)
    if any(_is_global_path(path) for path in files):
        projects = PR_DEFAULT_PROJECTS.copy()
        if mobile_related and "pixel7" not in projects:
            projects.append("pixel7")
        return _full_plan(projects)

    specs: set[str] = set()
    for path in files:
        specs.update(_category_specs_for(path))
        if _is_mobile_path(path):
            specs.update(MOBILE_SPECS)

    if not specs:
        return _full_plan(PR_DEFAULT_PROJECTS.copy())

    projects = PR_DEFAULT_PROJECTS.copy()
    if mobile_related and "pixel7" not in projects:
        projects.append("pixel7")

    desktop_specs = specs.difference(MOBILE_SPECS)
    if mobile_related and not desktop_specs:
        desktop_specs.update(DESKTOP_MOBILE_COMPANION_SPECS)

    matrix: list[E2ELeg] = []
    for project in projects:
        leg_specs = specs if project == "pixel7" else desktop_specs
        ordered = _ordered_specs(leg_specs)
        matrix.append(E2ELeg(project=project, spec_args=" ".join(shlex.quote(spec) for spec in ordered)))

    return E2EPlan(projects=projects, specs=_ordered_specs(specs), matrix=matrix)


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
