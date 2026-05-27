#!/usr/bin/env python3
"""Keep CI and local hook tool pins in sync."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised in CI preflight
    raise SystemExit("PyYAML is required: python -m pip install PyYAML") from exc

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "src" / "requirements.txt"
PRE_COMMIT = ROOT / ".pre-commit-config.yaml"
LINT_WORKFLOW = ROOT / ".github" / "workflows" / "lint.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require_match(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not find {label}.")
    return match.group(1)


def ruff_pre_commit_version() -> str:
    config = yaml.safe_load(read(PRE_COMMIT))
    for repo in config.get("repos", []):
        if repo.get("repo") == "https://github.com/astral-sh/ruff-pre-commit":
            return str(repo.get("rev", "")).removeprefix("v")
    raise SystemExit("Could not find ruff-pre-commit repo in .pre-commit-config.yaml.")


def local_bandit_version() -> str:
    config = yaml.safe_load(read(PRE_COMMIT))
    for repo in config.get("repos", []):
        if repo.get("repo") != "local":
            continue
        for hook in repo.get("hooks", []):
            deps = hook.get("additional_dependencies", [])
            for dep in deps:
                match = re.search(r"bandit(?:\[toml\])?==([0-9.]+)", dep)
                if match:
                    return match.group(1)
    raise SystemExit("Could not find local Bandit hook pin.")


def main() -> int:
    requirements = read(REQUIREMENTS)
    lint = read(LINT_WORKFLOW)

    expected_ruff = require_match(r"^ruff==([0-9.]+)\b", requirements, "ruff pin in src/requirements.txt")
    workflow_ruff = require_match(r"ruff==([0-9.]+)", lint, "ruff pin in .github/workflows/lint.yml")
    hook_ruff = ruff_pre_commit_version()

    expected_bandit = require_match(r"bandit\[toml\]==([0-9.]+)", lint, "Bandit pin in .github/workflows/lint.yml")
    hook_bandit = local_bandit_version()

    failures = []
    if workflow_ruff != expected_ruff:
        failures.append(f"Ruff workflow pin {workflow_ruff} != requirements pin {expected_ruff}")
    if hook_ruff != expected_ruff:
        failures.append(f"Ruff pre-commit pin {hook_ruff} != requirements pin {expected_ruff}")
    if hook_bandit != expected_bandit:
        failures.append(f"Bandit pre-commit pin {hook_bandit} != workflow pin {expected_bandit}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1

    print(f"Tool versions aligned: ruff=={expected_ruff}, bandit[toml]=={expected_bandit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
