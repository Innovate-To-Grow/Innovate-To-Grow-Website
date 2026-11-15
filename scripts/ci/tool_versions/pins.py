from __future__ import annotations

import re
from pathlib import Path

from .sources import (
    BANDIT,
    CI,
    DEPENDENCY_AUDIT,
    DEPLOY_ARCHIVE,
    DEPLOY_BACKEND,
    DEPLOY_FRONTEND,
    GITLEAKS_HOOK,
    IGNORE_VULN,
    LINT,
    MINOR,
    PIP_AUDIT,
    PLAYWRIGHT_IMAGE,
    POSTGRES_IMAGE,
    REQUIREMENTS,
    VERSION,
    Pin,
    Regex,
    Source,
    bandit_pre_commit_dependency,
    playwright_lock_version,
    ruff_pre_commit_rev,
    yaml_literal,
)

PIN_GROUPS: dict[str, tuple[Source, ...]] = {
    "ruff": (Regex(REQUIREMENTS, rf"^ruff=={VERSION}"), Regex(LINT, rf"ruff=={VERSION}"), ruff_pre_commit_rev),
    "bandit": (Regex(LINT, BANDIT), bandit_pre_commit_dependency),
    "gitleaks": (
        Regex(CI, rf'GITLEAKS_VERSION="{VERSION}"'),
        Regex(GITLEAKS_HOOK, re.escape("${GITLEAKS_VERSION:-") + VERSION),
    ),
    # Every image scan installs Trivy from GitHub releases: the backend and archive image jobs in ci.yml and the
    # archive deploy's scan before it publishes.
    "trivy": (
        Regex(CI, yaml_literal("TRIVY_VERSION"), minimum=2),
        Regex(DEPLOY_ARCHIVE, yaml_literal("TRIVY_VERSION")),
    ),
    # The smoke and E2E job containers.
    "playwright-image": (Regex(CI, PLAYWRIGHT_IMAGE, minimum=2),),
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
    ),
    "python-backend": (
        Regex(CI, yaml_literal("BACKEND_PYTHON_VERSION", MINOR)),
        Regex(DEPLOY_BACKEND, yaml_literal("python-version", MINOR)),
        Regex(DEPLOY_FRONTEND, yaml_literal("python-version", MINOR)),
        Regex(DEPLOY_ARCHIVE, yaml_literal("python-version", MINOR)),
    ),
    "python-tooling": (
        Regex(CI, yaml_literal("PYTHON_VERSION", MINOR)),
        Regex(LINT, yaml_literal("python-version", MINOR)),
        Regex(DEPENDENCY_AUDIT, yaml_literal("PYTHON_VERSION", MINOR)),
    ),
    "postgres": (Regex(CI, POSTGRES_IMAGE, minimum=4),),
    "pip-audit": (Regex(CI, PIP_AUDIT), Regex(DEPENDENCY_AUDIT, PIP_AUDIT)),
    # dependency-audit.yml re-runs ci.yml's python-dependency-audit weekly with the same accepted advisories,
    # which may be none.
    "pip-audit-ignores": (
        Regex(CI, IGNORE_VULN, minimum=0, as_set=True),
        Regex(DEPENDENCY_AUDIT, IGNORE_VULN, minimum=0, as_set=True),
    ),
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
