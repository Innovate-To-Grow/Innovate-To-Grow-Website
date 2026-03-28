#!/usr/bin/env python3
"""Repository structure checks for active first-party files."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINE_LIMIT = 200
DIRECTORY_LIMIT = 8

TRACKED_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".scss",
    ".ts",
    ".tsx",
}
COUNT_EXCLUDED_NAMES = {
    "__init__.py",
    "README.md",
    "index.ts",
    "index.tsx",
    "package.json",
    "tsconfig.app.json",
    "tsconfig.json",
    "tsconfig.node.json",
    "vite.config.ts",
}
EXCLUDED_DIR_NAMES = {
    ".git",
    ".github",
    ".idea",
    ".next",
    ".nuxt",
    ".output",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
EXCLUDED_PATH_PARTS = {
    "archive/legacy",
}
EXCLUDED_PATH_MARKERS = (
    "/migrations/",
    "/__pycache__/",
)
EXCLUDED_FILES = {
    ".coverage",
    "pages/package-lock.json",
    "src/db.sqlite3",
}


def relative_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def is_excluded(path: Path) -> bool:
    rel = relative_path(path)
    if path.name in EXCLUDED_FILES or rel in EXCLUDED_FILES:
        return True
    if any(marker in f"/{rel}/" for marker in EXCLUDED_PATH_MARKERS):
        return True
    return any(rel == item or rel.startswith(f"{item}/") for item in EXCLUDED_PATH_PARTS)


def iter_active_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if path.suffix not in TRACKED_SUFFIXES:
            continue
        if is_excluded(path):
            continue
        files.append(path)
    return files


def check_root_boundaries() -> list[str]:
    allowed = {
        ".claude",
        ".github",
        ".gitignore",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
        "archive",
        "aws",
        "docs",
        "pages",
        "pyproject.toml",
        "qodana.yaml",
        "src",
    }
    ignored_local = {".idea", ".ruff_cache"}
    unexpected = []
    for child in sorted(REPO_ROOT.iterdir(), key=lambda p: p.name):
        if child.name.startswith(".git"):
            continue
        if child.name in allowed or child.name in ignored_local:
            continue
        unexpected.append(child.name)
    return unexpected


def read_line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def main() -> int:
    violations: list[str] = []

    unexpected_root_items = check_root_boundaries()
    if unexpected_root_items:
        violations.append("unexpected top-level items: " + ", ".join(unexpected_root_items))

    active_files = iter_active_files()

    too_long = []
    directory_counts: defaultdict[str, list[str]] = defaultdict(list)
    for path in active_files:
        rel = relative_path(path)
        line_count = read_line_count(path)
        if line_count > LINE_LIMIT:
            too_long.append((line_count, rel))
        if path.name not in COUNT_EXCLUDED_NAMES:
            directory_counts[str(path.parent.relative_to(REPO_ROOT))].append(path.name)

    if too_long:
        formatted = ", ".join(f"{rel} ({count})" for count, rel in sorted(too_long))
        violations.append(f"files over {LINE_LIMIT} lines: {formatted}")

    overfull_dirs = []
    for directory, names in sorted(directory_counts.items()):
        if len(names) > DIRECTORY_LIMIT:
            overfull_dirs.append((directory, len(names), sorted(names)))
    if overfull_dirs:
        formatted = ", ".join(f"{directory} ({count}: {', '.join(names)})" for directory, count, names in overfull_dirs)
        violations.append(f"directories over {DIRECTORY_LIMIT} files: {formatted}")

    if violations:
        print("Repository structure check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Repository structure check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
