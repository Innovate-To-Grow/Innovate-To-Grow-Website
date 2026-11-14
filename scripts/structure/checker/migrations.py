"""Migration guard (spec R024): an existing file under a protected ``migrations/`` path never changes.

Compares the merge base of ``base`` and ``head`` with ``head`` (the same three-dot diff the CI ``changes`` job
plans from). Added files pass, so new migrations keep working; a modified, deleted, renamed or type-changed
existing file fails unless ``[migrations].allowed_changes`` lists it with a reason.
"""

from __future__ import annotations

import subprocess  # nosec B404 - runs git with fixed arguments
from dataclasses import dataclass
from pathlib import Path

from scripts.structure.checker.config import Config, glob_match

ZERO_SHA = "0" * 40
VERBS = {"M": "modified", "D": "deleted", "R": "renamed", "T": "changed type"}


class GuardError(RuntimeError):
    """The commits to compare cannot be resolved."""


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    new_path: str | None = None

    def describe(self) -> str:
        verb = VERBS.get(self.status[0], f"changed ({self.status})")
        target = f" to {self.new_path}" if self.new_path else ""
        return f"{self.path} was {verb}{target}"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(  # nosec B603 B607 - fixed git arguments
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise GuardError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def _is_commit(root: Path, ref: str) -> bool:
    try:
        _git(root, "cat-file", "-e", f"{ref}^{{commit}}")
    except GuardError:
        return False
    return True


def resolve_base(root: Path, base: str, head: str) -> str | None:
    """The commit to diff from: merge-base(base, head), else head's first parent, else ``None``."""
    if base and base != ZERO_SHA and _is_commit(root, base):
        return _git(root, "merge-base", base, head).strip()
    if _is_commit(root, f"{head}^1"):
        return _git(root, "rev-parse", f"{head}^1").strip()
    return None


def parse_name_status(output: str) -> list[Change]:
    """Parse ``git diff --name-status -z``: renames and copies carry two paths."""
    tokens = [token for token in output.split("\0") if token]
    changes, index = [], 0
    while index < len(tokens):
        status = tokens[index]
        if status[0] in "RC":
            changes.append(Change(status, tokens[index + 1], tokens[index + 2]))
            index += 3
        else:
            changes.append(Change(status, tokens[index + 1]))
            index += 2
    return changes


def changed_paths(root: Path, base: str, head: str) -> list[Change]:
    output = _git(root, "diff", "--name-status", "-z", "--find-renames", "--no-ext-diff", base, head)
    return parse_name_status(output)


def is_protected(path: str, config: Config) -> bool:
    return any(glob_match(pattern, path) for pattern in config.protected_migrations)


def protected_changes(changes: list[Change], config: Config) -> list[Change]:
    """Changes to existing protected files. Additions and copies leave every existing file untouched."""
    problems = []
    for change in changes:
        if change.status[0] in "AC" or not is_protected(change.path, config):
            continue
        if not any(entry.matches(change.path) for entry in config.allowed_migration_changes):
            problems.append(change)
    return problems


def run_guard(root: Path, base: str, head: str, config: Config) -> int:
    """Print the guard's verdict; return 1 when an existing migration changed, else 0."""
    start = resolve_base(root, base, head)
    if start is None:
        print(f"Migration guard: {head} has no parent and no usable base; nothing to compare.")
        return 0
    changes = changed_paths(root, start, head)
    problems = protected_changes(changes, config)
    added = sum(1 for change in changes if change.status == "A" and is_protected(change.path, config))
    print(f"Migration guard: compared {start[:12]}..{head[:12]}; {added} protected file(s) added.")
    for problem in problems:
        print(f"ERROR: {problem.describe()}. Existing migrations are read-only: add a new migration instead.")
    return 1 if problems else 0
