"""Shared test helpers: small-limit configs and throwaway git repositories."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from scripts.structure.checker.config import Config, Entry, Limits, Measure

GIT_IDENTITY = ["-c", "user.name=Structure Test", "-c", "user.email=structure@example.invalid"]


def make_config(**overrides) -> Config:
    config = Config(
        limits=Limits(file_lines=3, directory_files=2, directory_subdirs=2, module_depth=2),
        measure=Measure(
            source_extensions=frozenset({".py", ".ts"}),
            source_names=frozenset({"Dockerfile"}),
            entry_files=("**/__init__.py", "app/features/*/index.ts"),
            module_roots=("app/features/*",),
            banned_directory_names=frozenset({"misc"}),
        ),
        unmeasured=(Entry(("vendor/**",), "third-party"),),
        exceptions=(),
        protected_migrations=("**/migrations/**",),
        allowed_migration_changes=(),
    )
    return replace(config, **overrides)


def write(root: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


class GitRepository:
    """A temporary repository; ``commit`` returns the new commit's SHA."""

    def __init__(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        command = ["git", *GIT_IDENTITY, "-C", str(self.root), *args]
        return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, files: dict[str, str] | None = None, remove: tuple[str, ...] = ()) -> str:
        write(self.root, files or {})
        for path in remove:
            self.git("rm", "-q", path)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def close(self) -> None:
        self._directory.cleanup()
