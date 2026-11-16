"""Evaluate the structure rules over a measured tree and apply the recorded exceptions.

* R001 — a measured source file has more than ``file_lines`` physical lines.
* R002 — a directory holds more than ``directory_files`` files directly (entry files excluded).
* R003-mixed — a directory holds both files (entry files excluded) and subdirectories.
* R003-width — a directory holds more than ``directory_subdirs`` subdirectories.
* R004-depth — a file sits more than ``module_depth`` levels below its business-module root (advisory).
* R004-name — a directory is named like a dumping ground (``misc``, ``others``, ``temp`` …).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from scripts.structure.checker.config import Config, Entry, glob_match
from scripts.structure.checker.tree import Tree, count_lines, join

ADVISORY_RULES = frozenset({"R004-depth"})


@dataclass(frozen=True, order=True)
class Finding:
    rule: str
    path: str
    value: int
    limit: int

    @property
    def advisory(self) -> bool:
        return self.rule in ADVISORY_RULES

    def describe(self) -> str:
        detail = {
            "R001": f"{self.value} lines (limit {self.limit})",
            "R002": f"{self.value} files (limit {self.limit})",
            "R003-mixed": f"{self.value} file{'' if self.value == 1 else 's'} beside subdirectories",
            "R003-width": f"{self.value} subdirectories (limit {self.limit})",
            "R004-depth": f"{self.value} levels below its module (advisory limit {self.limit})",
            "R004-name": "directory name says nothing about its responsibility",
        }[self.rule]
        return f"{self.rule:<10} {self.path}  {detail}"


@dataclass
class Outcome:
    active: list[Finding] = field(default_factory=list)
    excepted: dict[Entry, list[Finding]] = field(default_factory=dict)
    stale_exceptions: list[Entry] = field(default_factory=list)
    stale_unmeasured: list[Entry] = field(default_factory=list)

    @property
    def failing(self) -> bool:
        """What enforce mode fails on: a non-advisory finding or a stale entry."""
        hard = any(not finding.advisory for finding in self.active)
        return hard or bool(self.stale_exceptions or self.stale_unmeasured)


def file_findings(tree: Tree, config: Config) -> Iterator[Finding]:
    limit = config.limits.file_lines
    for path in tree.files:
        if config.measure.is_source(path):
            lines = count_lines(tree.root / path)
            if lines > limit:
                yield Finding("R001", path, lines, limit)


def directory_findings(tree: Tree, config: Config) -> Iterator[Finding]:
    limits, measure = config.limits, config.measure
    for name, directory in sorted(tree.directories.items()):
        files = [file for file in directory.files if not measure.is_entry_file(join(name, file))]
        if len(files) > limits.directory_files:
            yield Finding("R002", name, len(files), limits.directory_files)
        if files and directory.subdirs:
            yield Finding("R003-mixed", name, len(files), 0)
        if len(directory.subdirs) > limits.directory_subdirs:
            yield Finding("R003-width", name, len(directory.subdirs), limits.directory_subdirs)
        if name != "." and PurePosixPath(name).name in measure.banned_directory_names:
            yield Finding("R004-name", name, 0, 0)


def module_root(path: str, patterns: tuple[str, ...]) -> str | None:
    """The deepest directory above ``path`` that matches a business-module root pattern."""
    parts = PurePosixPath(path).parts
    for depth in range(len(parts) - 1, 0, -1):
        prefix = join(*parts[:depth])
        if any(glob_match(pattern, prefix) for pattern in patterns):
            return prefix
    return None


def depth_findings(tree: Tree, config: Config) -> Iterator[Finding]:
    limit = config.limits.module_depth
    for path in tree.files:
        root = module_root(path, config.measure.module_roots)
        if root is not None:
            depth = len(PurePosixPath(path).parts) - len(PurePosixPath(root).parts)
            if depth > limit:
                yield Finding("R004-depth", path, depth, limit)


def evaluate(tree: Tree, config: Config) -> list[Finding]:
    found = [*file_findings(tree, config), *directory_findings(tree, config), *depth_findings(tree, config)]
    return sorted(found)


def apply_exceptions(findings: list[Finding], tree: Tree, config: Config) -> Outcome:
    """Split findings into active and excepted ones, and list entries that no longer match anything."""
    outcome = Outcome()
    for finding in findings:
        entries = [entry for entry in config.exceptions if finding.rule in entry.rules and entry.matches(finding.path)]
        if not entries:
            outcome.active.append(finding)
        for entry in entries:
            outcome.excepted.setdefault(entry, []).append(finding)
    outcome.stale_exceptions = [entry for entry in config.exceptions if entry not in outcome.excepted]
    outcome.stale_unmeasured = [config.unmeasured[index] for index in tree.unused_unmeasured]
    return outcome
