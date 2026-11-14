"""The measured tree: tracked files minus the unmeasured ones, indexed by directory."""

from __future__ import annotations

import subprocess  # nosec B404 - runs git with fixed arguments
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from scripts.structure.checker.config import Config


@dataclass
class Directory:
    """Direct children of one directory: file names and subdirectory names."""

    files: list[str] = field(default_factory=list)
    subdirs: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Tree:
    root: Path
    files: tuple[str, ...]
    directories: dict[str, Directory]
    unused_unmeasured: tuple[int, ...]


def join(*parts: str) -> str:
    """Join path segments; the repository root is ``.``."""
    return "/".join(part for part in parts if part and part != ".") or "."


def tracked_files(root: Path) -> list[str]:
    """Files in git's index that exist in the working tree (untracked and ignored files never count)."""
    result = subprocess.run(  # nosec B603 B607 - fixed git arguments
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    )
    paths = (path for path in result.stdout.decode("utf-8").split("\0") if path)
    return sorted(path for path in paths if (root / path).is_file())


def index_directories(paths: list[str]) -> dict[str, Directory]:
    directories: dict[str, Directory] = defaultdict(Directory)
    for path in paths:
        parts = PurePosixPath(path).parts
        directories[join(*parts[:-1])].files.append(parts[-1])
        for depth in range(len(parts) - 1):
            directories[join(*parts[:depth])].subdirs.add(parts[depth])
    return dict(directories)


def build_tree(root: Path, config: Config, paths: list[str] | None = None) -> Tree:
    """Drop unmeasured paths (migrations, third-party, generated, historical) and index the rest."""
    used: set[int] = set()
    measured = []
    for path in tracked_files(root) if paths is None else paths:
        hits = {index for index, entry in enumerate(config.unmeasured) if entry.matches(path)}
        used |= hits
        if not hits:
            measured.append(path)
    unused = tuple(index for index in range(len(config.unmeasured)) if index not in used)
    return Tree(root, tuple(measured), index_directories(measured), unused)


def count_lines(path: Path) -> int:
    """Physical lines: blank and comment lines count, a missing final newline still ends a line."""
    data = path.read_bytes()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
