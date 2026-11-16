from __future__ import annotations

import contextlib
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


CI = ".github/workflows/ci.yml"


DEPENDENCY_AUDIT = ".github/workflows/dependency-audit.yml"


PRE_COMMIT = ".pre-commit-config.yaml"


PACKAGE_LOCK = "pages/package-lock.json"


DIGEST = "0123456789abcdef" * 4


IMAGE = f"mcr.microsoft.com/playwright:v1.64.0-noble@sha256:{DIGEST}"


IGNORED = "GHSA-aaaa-bbbb-cccc,PYSEC-2026-1"


# The smallest checkout every source can read, with multi-occurrence sources at exactly their minimum
# count. `<image>` stands for IMAGE.
ALIGNED_FILES = {
    "src/requirements/local.txt": "-r production.txt\n\n# Linter / formatter\nruff==0.17.2\n",
    ".github/workflows/lint.yml": """\
steps:
  - with:
      python-version: "3.11"
  - run: pip install ruff==0.17.2 "bandit[toml]==1.7.10"
""",
    PRE_COMMIT: """\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.2
    hooks:
      - id: ruff
  - repo: local
    hooks:
      - id: gitleaks
        entry: bash scripts/pre-commit/gitleaks-protect.sh
      - id: bandit-baseline
        additional_dependencies: ["bandit[toml]==1.7.10"]
""",
    "scripts/pre-commit/gitleaks-protect.sh": 'gitleaks_version="${GITLEAKS_VERSION:-8.21.2}"\n',
    CI: """\
env:
  PYTHON_VERSION: "3.11"
  BACKEND_PYTHON_VERSION: "3.14"
  NODE_VERSION: "22.22.2"
jobs:
  secrets-scan:
    steps:
      - run: GITLEAKS_VERSION="8.21.2"
  backend-tests:
    services:
      postgres:
        image: postgres:16
  migration-check:
    services:
      postgres:
        image: postgres:16
  frontend-chromium-smoke:
    container:
      image: "<image>"
  python-dependency-audit:
    steps:
      - run: pip install "pip-audit==2.7.3"
      - run: pip-audit --ignore-vuln GHSA-aaaa-bbbb-cccc --ignore-vuln PYSEC-2026-1
  backend-docker-smoke:
    steps:
      - run: postgres_image="postgres:16"
  backend-docker-build:
    steps:
      - env:
          TRIVY_VERSION: "0.70.0"
  archive-docker-build:
    steps:
      - env:
          TRIVY_VERSION: "0.70.0"
  e2e:
    container:
      image: "<image>"
    services:
      postgres:
        image: postgres:16
    steps:
      - uses: ./.github/actions/setup-backend-venv
        with:
          cache-label: pw-v1.64.0-noble
""",
    # The same advisories in another order, behind a comment that mentions the flag in prose.
    DEPENDENCY_AUDIT: """\
env:
  PYTHON_VERSION: "3.11"
  NODE_VERSION: "22.22.2"
steps:
  - run: pip install "pip-audit==2.7.3"
  # Keep the --ignore-vuln list in sync with the python-dependency-audit job in ci.yml.
  - run: pip-audit --ignore-vuln PYSEC-2026-1 --ignore-vuln GHSA-aaaa-bbbb-cccc
""",
    ".github/workflows/deploy-backend.yml": 'steps:\n  - with:\n      python-version: "3.14"\n',
    ".github/workflows/deploy-archive.yml": """\
steps:
  - with:
      python-version: "3.14"
  - env:
      TRIVY_VERSION: "0.70.0"
""",
    ".github/workflows/deploy-frontend.yml": """\
steps:
  - with:
      python-version: "3.14"
  - with:
      node-version: "22.22.2"
""",
    PACKAGE_LOCK: json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"devDependencies": {"@playwright/test": "1.64.0"}},
                "node_modules/@playwright/test": {"version": "1.64.0"},
            },
        },
        indent=2,
    ),
}


# Every group, in report order, with the value the fixture pins and the number of sources reading it.
EXPECTED = {
    "ruff": ("0.17.2", 3),
    "bandit": ("1.7.10", 2),
    "gitleaks": ("8.21.2", 2),
    "trivy": ("0.70.0", 2),
    "playwright-image": (IMAGE, 1),
    "playwright": ("1.64.0", 3),
    "node": ("22.22.2", 3),
    "python-backend": ("3.14", 4),
    "python-tooling": ("3.11", 3),
    "postgres": ("16", 1),
    "pip-audit": ("2.7.3", 2),
    "pip-audit-ignores": (IGNORED, 2),
}


# (group, file, old text, new text, aligned value, drifted value): each edit moves exactly one source.
DRIFTS = (
    ("ruff", PRE_COMMIT, "rev: v0.17.2", "rev: v0.18.0", "0.17.2", "0.18.0"),
    ("ruff", "src/requirements/local.txt", "ruff==0.17.2", "ruff==0.18.0", "0.17.2", "0.18.0"),
    ("bandit", PRE_COMMIT, "bandit[toml]==1.7.10", "bandit[toml]==1.8.0", "1.7.10", "1.8.0"),
    ("gitleaks", "scripts/pre-commit/gitleaks-protect.sh", ":-8.21.2", ":-8.22.0", "8.21.2", "8.22.0"),
    # The likely slip: bumping the CI scans but not the archive deploy's, or one CI scan but not the other.
    ("trivy", ".github/workflows/deploy-archive.yml", '"0.70.0"', '"0.71.0"', "0.70.0", "0.71.0"),
    ("trivy", CI, 'TRIVY_VERSION: "0.70.0"', 'TRIVY_VERSION: "0.71.0"', "0.70.0", "0.71.0"),
    # One of ci.yml's two job containers, the Chromium smoke's, moves alone.
    ("playwright-image", CI, DIGEST, "f" * 64, IMAGE, IMAGE.replace(DIGEST, "f" * 64)),
    ("playwright", CI, "pw-v1.64.0-noble", "pw-v1.62.1-noble", "1.64.0", "1.62.1"),
    ("playwright", PACKAGE_LOCK, '"version": "1.64.0"', '"version": "1.65.0"', "1.64.0", "1.65.0"),
    ("node", DEPENDENCY_AUDIT, 'NODE_VERSION: "22.22.2"', 'NODE_VERSION: "22.22.3"', "22.22.2", "22.22.3"),
    ("node", ".github/workflows/deploy-frontend.yml", '"22.22.2"', '"22.22.3"', "22.22.2", "22.22.3"),
    ("python-backend", ".github/workflows/deploy-backend.yml", '"3.14"', '"3.15"', "3.14", "3.15"),
    ("python-backend", ".github/workflows/deploy-archive.yml", '"3.14"', '"3.13"', "3.14", "3.13"),
    ("python-tooling", ".github/workflows/lint.yml", '"3.11"', '"3.12"', "3.11", "3.12"),
    ("python-tooling", DEPENDENCY_AUDIT, 'PYTHON_VERSION: "3.11"', 'PYTHON_VERSION: "3.12"', "3.11", "3.12"),
    ("postgres", CI, "postgres:16", "postgres:17", "16", "17"),
    ("pip-audit", DEPENDENCY_AUDIT, "==2.7.3", "==2.8.0", "2.7.3", "2.8.0"),
    ("pip-audit-ignores", DEPENDENCY_AUDIT, "--ignore-vuln PYSEC-2026-1 ", "", IGNORED, "GHSA-aaaa-bbbb-cccc"),
)


@contextlib.contextmanager
def fake_repository() -> Iterator[Path]:
    """A temporary checkout holding ALIGNED_FILES, so every pin group agrees."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for path, content in ALIGNED_FILES.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(content.replace("<image>", IMAGE), encoding="utf-8")
        yield root


def replace_once(root: Path, path: str, old: str, new: str) -> None:
    file = root / path
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"{old!r} is not in the {path} fixture")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")
