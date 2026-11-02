#!/usr/bin/env python3
"""Keep tool and runtime version pins in sync across CI, deploy workflows, git hooks and the AWS runner image.

Each pin group lists every place one version is written down, and all of them must agree. A source that
finds fewer matches than it expects is an error rather than a silent skip, so a renamed key or a rewritten
line cannot quietly drop out of the check. (src/Dockerfile vs BACKEND_PYTHON_VERSION is guarded by
scripts/ci/tests/test_ci_workflow_invariants.py instead.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised in CI preflight
    raise SystemExit("PyYAML is required: python -m pip install PyYAML") from exc

ROOT = Path(__file__).resolve().parents[2]

CI = ".github/workflows/ci.yml"
LINT = ".github/workflows/lint.yml"
DEPENDENCY_AUDIT = ".github/workflows/dependency-audit.yml"
DEPLOY_BACKEND = ".github/workflows/deploy-backend.yml"
DEPLOY_FRONTEND = ".github/workflows/deploy-frontend.yml"
DEPLOY_ARCHIVE = ".github/workflows/deploy-archive.yml"
RUNNER_SMOKE = ".github/workflows/aws-runner-smoke.yml"
BAKE_IMAGE = "aws/ci-runners/bake-image.sh"
IMAGE_TF = "aws/ci-runners/image.tf"
# src/requirements.txt is a thin `-r requirements/local.txt` entrypoint, so the ruff pin lives here.
REQUIREMENTS = "src/requirements/local.txt"
PRE_COMMIT = ".pre-commit-config.yaml"
GITLEAKS_HOOK = "scripts/pre-commit/gitleaks-protect.sh"
PACKAGE_LOCK = "pages/package-lock.json"
RUFF_PRE_COMMIT = "https://github.com/astral-sh/ruff-pre-commit"

VERSION = r"(\d+(?:\.\d+)*)"
MINOR = r"(\d+\.\d+)"  # Python is compared by minor version; a patch component after it is ignored.
BANDIT = rf"bandit(?:\[toml\])?=={VERSION}"
PIP_AUDIT = rf"pip-audit(?:\[cyclonedx\])?=={VERSION}"
PLAYWRIGHT_IMAGE = r"(mcr\.microsoft\.com/playwright:[\w.-]+@sha256:[0-9a-f]{64})"
POSTGRES_IMAGE = r"\bpostgres:(\d+)"
# Advisory IDs only (GHSA-..., PYSEC-..., CVE-...), so prose such as "the --ignore-vuln list" is not read as one.
IGNORE_VULN = r"--ignore-vuln[= ]([A-Z]+-[\w-]+)"
# bake-image.sh installs both interpreters in one loop, tooling first and backend second (the order ci.yml
# declares PYTHON_VERSION and BACKEND_PYTHON_VERSION in). A third version fails both patterns on purpose.
BAKED_TOOLING_PYTHON = r"^for version in (\d+\.\d+)\.\d+ \d+\.\d+\.\d+; do$"
BAKED_BACKEND_PYTHON = r"^for version in \d+\.\d+\.\d+ (\d+\.\d+)\.\d+; do$"

Pin = tuple[str, str]  # (source label, value)
Source = Callable[[Path], list[Pin]]


class PinError(Exception):
    """A source could not find its pin: missing file, renamed key, or fewer matches than expected."""


def read(root: Path, path: str) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PinError(f"{path}: cannot read ({exc.strerror or exc})") from exc


def yaml_literal(key: str, value: str = VERSION) -> str:
    """``key: value`` with a literal, optionally quoted value; ``${{ env.* }}`` expressions never match."""
    return rf"""\b{key}: ["']?{value}"""


@dataclass(frozen=True)
class Regex:
    """Group 1 of every ``regex`` match in ``path``; fewer than ``minimum`` matches raise PinError.

    Each distinct value becomes one pin labelled with the lines it was found on. With ``as_set`` the file
    yields a single pin instead: the sorted, comma-joined set of every matched value.
    """

    path: str
    regex: str
    minimum: int = 1
    as_set: bool = False

    def __call__(self, root: Path) -> list[Pin]:
        text = read(root, self.path)
        matches = list(re.finditer(self.regex, text, re.MULTILINE))
        if len(matches) < self.minimum:
            raise PinError(
                f"{self.path}: expected at least {self.minimum} match(es) of /{self.regex}/, found {len(matches)}"
            )
        if self.as_set:
            return [(self.path, ",".join(sorted({match.group(1) for match in matches})))]
        lines: dict[str, set[int]] = {}
        for match in matches:
            lines.setdefault(match.group(1), set()).add(text.count("\n", 0, match.start(1)) + 1)
        return [(f"{self.path}:{','.join(map(str, sorted(numbers)))}", value) for value, numbers in lines.items()]


def _pre_commit_repos(root: Path) -> list[dict]:
    return (yaml.safe_load(read(root, PRE_COMMIT)) or {}).get("repos") or []


def ruff_pre_commit_rev(root: Path) -> list[Pin]:
    """The ruff-pre-commit hook revision without its leading ``v``."""
    for repo in _pre_commit_repos(root):
        if repo.get("repo") == RUFF_PRE_COMMIT:
            return [(f"{PRE_COMMIT} ruff-pre-commit rev", str(repo.get("rev", "")).removeprefix("v"))]
    raise PinError(f"{PRE_COMMIT}: no `repo: {RUFF_PRE_COMMIT}` entry")


def bandit_pre_commit_dependency(root: Path) -> list[Pin]:
    """Bandit as pinned in the additional_dependencies of a local hook."""
    local_repos = [repo for repo in _pre_commit_repos(root) if repo.get("repo") == "local"]
    pins = [
        (f"{PRE_COMMIT} {hook.get('id')} hook", match.group(1))
        for repo in local_repos
        for hook in repo.get("hooks") or []
        for dependency in hook.get("additional_dependencies") or []
        if (match := re.match(BANDIT, str(dependency)))
    ]
    if not pins:
        raise PinError(f"{PRE_COMMIT}: no local hook lists /{BANDIT}/ in additional_dependencies")
    return pins


def playwright_lock_version(root: Path) -> list[Pin]:
    """The ``@playwright/test`` version resolved in the npm lockfile."""
    package = json.loads(read(root, PACKAGE_LOCK)).get("packages", {}).get("node_modules/@playwright/test", {})
    if not package.get("version"):
        raise PinError(f'{PACKAGE_LOCK}: no packages["node_modules/@playwright/test"].version')
    return [(f"{PACKAGE_LOCK} @playwright/test", package["version"])]


PIN_GROUPS: dict[str, tuple[Source, ...]] = {
    "ruff": (Regex(REQUIREMENTS, rf"^ruff=={VERSION}"), Regex(LINT, rf"ruff=={VERSION}"), ruff_pre_commit_rev),
    "bandit": (Regex(LINT, BANDIT), bandit_pre_commit_dependency),
    "gitleaks": (
        Regex(CI, rf'GITLEAKS_VERSION="{VERSION}"'),
        Regex(GITLEAKS_HOOK, re.escape("${GITLEAKS_VERSION:-") + VERSION),
    ),
    # The smoke and E2E job containers, the runner-image pre-pull and the runner smoke test.
    "playwright-image": (
        Regex(CI, PLAYWRIGHT_IMAGE, minimum=2),
        Regex(RUNNER_SMOKE, PLAYWRIGHT_IMAGE),
        Regex(BAKE_IMAGE, PLAYWRIGHT_IMAGE),
    ),
    # The image's browsers must be the ones @playwright/test drives; the E2E venv cache label names them too.
    "playwright": (
        Regex(CI, r"mcr\.microsoft\.com/playwright:v(\d+\.\d+\.\d+)-noble", minimum=2),
        Regex(CI, r"pw-v(\d+\.\d+\.\d+)-noble"),
        playwright_lock_version,
    ),
    "node": (
        Regex(CI, yaml_literal("NODE_VERSION")),
        Regex(DEPENDENCY_AUDIT, yaml_literal("NODE_VERSION")),
        Regex(DEPLOY_FRONTEND, yaml_literal("node-version")),
        Regex(RUNNER_SMOKE, yaml_literal("node-version")),
        # Download URLs and checksum lookup (4), and the tool-cache directory setup-node resolves (4).
        Regex(BAKE_IMAGE, rf"(?:/dist/v|node-v|/node/){VERSION}", minimum=8),
        Regex(IMAGE_TF, re.escape("node --version | grep '^v") + VERSION),
    ),
    "python-backend": (
        Regex(CI, yaml_literal("BACKEND_PYTHON_VERSION", MINOR)),
        Regex(DEPLOY_BACKEND, yaml_literal("python-version", MINOR)),
        Regex(DEPLOY_FRONTEND, yaml_literal("python-version", MINOR)),
        Regex(DEPLOY_ARCHIVE, yaml_literal("python-version", MINOR)),
        Regex(RUNNER_SMOKE, yaml_literal("python-version", MINOR)),
        Regex(BAKE_IMAGE, BAKED_BACKEND_PYTHON),
    ),
    "python-tooling": (
        Regex(CI, yaml_literal("PYTHON_VERSION", MINOR)),
        Regex(LINT, yaml_literal("python-version", MINOR)),
        Regex(DEPENDENCY_AUDIT, yaml_literal("PYTHON_VERSION", MINOR)),
        Regex(BAKE_IMAGE, BAKED_TOOLING_PYTHON),
    ),
    "postgres": (
        Regex(CI, POSTGRES_IMAGE, minimum=5),
        Regex(RUNNER_SMOKE, POSTGRES_IMAGE),
        Regex(BAKE_IMAGE, POSTGRES_IMAGE),
    ),
    "pip-audit": (Regex(CI, PIP_AUDIT, minimum=2), Regex(DEPENDENCY_AUDIT, PIP_AUDIT)),
    # dependency-audit.yml re-runs ci.yml's python-security-audit weekly with the same accepted advisories.
    "pip-audit-ignores": (Regex(CI, IGNORE_VULN, as_set=True), Regex(DEPENDENCY_AUDIT, IGNORE_VULN, as_set=True)),
}


def collect_pins(root: Path) -> dict[str, list[Pin]]:
    """``{group: [(source, value), ...]}`` for every pin group, read from the checkout at ``root``."""
    return {group: [pin for source in sources for pin in source(root)] for group, sources in PIN_GROUPS.items()}


def mismatches(pins: dict[str, list[Pin]]) -> list[str]:
    """One line per group whose sources disagree, listing each value with the sources that pin it."""
    problems = []
    for group, group_pins in pins.items():
        sources_by_value: dict[str, list[str]] = {}
        for source, value in group_pins:
            sources_by_value.setdefault(value, []).append(source)
        if len(sources_by_value) > 1:
            listed = " vs ".join(f"{value} ({', '.join(sources)})" for value, sources in sources_by_value.items())
            problems.append(f"{group}: {listed}")
    return problems


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


if __name__ == "__main__":
    raise SystemExit(main())
