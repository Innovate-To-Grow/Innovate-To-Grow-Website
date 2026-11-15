from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised in CI preflight
    raise SystemExit("PyYAML is required: python -m pip install PyYAML") from exc


ROOT = Path(__file__).resolve().parents[3]


CI = ".github/workflows/ci.yml"


LINT = ".github/workflows/lint.yml"


DEPENDENCY_AUDIT = ".github/workflows/dependency-audit.yml"


DEPLOY_BACKEND = ".github/workflows/deploy-backend.yml"


DEPLOY_FRONTEND = ".github/workflows/deploy-frontend.yml"


DEPLOY_ARCHIVE = ".github/workflows/deploy-archive.yml"


# src/requirements.txt is a thin `-r requirements/local.txt` entrypoint, so the ruff pin lives here.
REQUIREMENTS = "src/requirements/local.txt"


PRE_COMMIT = ".pre-commit-config.yaml"


GITLEAKS_HOOK = "scripts/pre-commit/gitleaks-protect.sh"


PACKAGE_LOCK = "pages/package-lock.json"


RUFF_PRE_COMMIT = "https://github.com/astral-sh/ruff-pre-commit"


VERSION = r"(\d+(?:\.\d+)*)"


MINOR = r"(\d+\.\d+)"  # Python is compared by minor version; a patch component after it is ignored.


BANDIT = rf"bandit(?:\[toml\])?=={VERSION}"


PIP_AUDIT = rf"pip-audit=={VERSION}"


PLAYWRIGHT_IMAGE = r"(mcr\.microsoft\.com/playwright:[\w.-]+@sha256:[0-9a-f]{64})"


POSTGRES_IMAGE = r"\bpostgres:(\d+)"


# Advisory IDs only (GHSA-..., PYSEC-..., CVE-...), so prose such as "the --ignore-vuln list" is not read as one.
IGNORE_VULN = r"--ignore-vuln[= ]([A-Z]+-[\w-]+)"


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
    yields a single pin instead: the sorted, comma-joined set of every matched value, or ``none``.
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
            return [(self.path, ",".join(sorted({match.group(1) for match in matches})) or "none")]
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
