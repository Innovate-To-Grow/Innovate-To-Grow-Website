"""Load ``structure.toml``: limits, what is measured, exceptions and the protected migration paths."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name("structure.toml")
RULES = ("R001", "R002", "R003-mixed", "R003-width", "R004-depth", "R004-name")


class ConfigError(ValueError):
    """``structure.toml`` is missing, malformed, or names an unknown rule."""


@cache
def _compile(pattern: str) -> re.Pattern[str]:
    """Translate a path glob: ``*`` stays inside one path segment, ``**/`` spans any number of them."""
    parts, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:[^/]+/)*")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        else:
            char = pattern[index]
            parts.append({"*": "[^/]*", "?": "[^/]"}.get(char, re.escape(char)))
            index += 1
    return re.compile("".join(parts) + r"\Z")


def glob_match(pattern: str, path: str) -> bool:
    """Whether a repository-relative POSIX path (``.`` for the root) matches ``pattern``."""
    return _compile(pattern).match(path) is not None


@dataclass(frozen=True)
class Entry:
    """Path patterns treated specially, the rules that applies to, and why."""

    patterns: tuple[str, ...]
    reason: str
    rules: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        return any(glob_match(pattern, path) for pattern in self.patterns)

    @property
    def label(self) -> str:
        scope = f" [{', '.join(self.rules)}]" if self.rules else ""
        return f"{', '.join(self.patterns)}{scope}"


@dataclass(frozen=True)
class Limits:
    file_lines: int
    directory_files: int
    directory_subdirs: int
    module_depth: int


@dataclass(frozen=True)
class Measure:
    source_extensions: frozenset[str]
    source_names: frozenset[str]
    entry_files: tuple[str, ...]
    module_roots: tuple[str, ...]
    banned_directory_names: frozenset[str]

    def is_source(self, path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        return name in self.source_names or any(name.endswith(ext) for ext in self.source_extensions)

    def is_entry_file(self, path: str) -> bool:
        return any(glob_match(pattern, path) for pattern in self.entry_files)


@dataclass(frozen=True)
class Config:
    limits: Limits
    measure: Measure
    unmeasured: tuple[Entry, ...]
    exceptions: tuple[Entry, ...]
    protected_migrations: tuple[str, ...]
    allowed_migration_changes: tuple[Entry, ...]


def _table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"missing [{key}] table")
    return value


def _strings(raw: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{where}: `{key}` must be a list of non-empty strings")
    return tuple(value)


def _entry(raw: dict[str, Any], where: str, *, with_rules: bool) -> Entry:
    patterns = _strings(raw, "paths", where)
    reason = raw.get("reason")
    if not patterns or not isinstance(reason, str) or not reason.strip():
        raise ConfigError(f"{where}: every entry needs `paths` and a `reason`")
    rules = _strings(raw, "rules", where) if with_rules else ()
    unknown = sorted(set(rules) - set(RULES))
    if with_rules and (not rules or unknown):
        raise ConfigError(f"{where}: `rules` must name some of {', '.join(RULES)} (unknown: {unknown})")
    return Entry(patterns, reason.strip(), rules)


def _entries(raw: dict[str, Any], key: str, *, with_rules: bool) -> tuple[Entry, ...]:
    items = raw.get(key, [])
    if not isinstance(items, list):
        raise ConfigError(f"`{key}` must be an array of tables")
    return tuple(_entry(item, f"{key}[{i}]", with_rules=with_rules) for i, item in enumerate(items))


def _limits(raw: dict[str, Any]) -> Limits:
    try:
        limits = Limits(**raw)
    except TypeError as error:
        raise ConfigError(f"[limits]: {error}") from error
    if not all(isinstance(value, int) and value > 0 for value in vars(limits).values()):
        raise ConfigError("[limits]: every limit must be a positive integer")
    return limits


def _measure(raw: dict[str, Any]) -> Measure:
    return Measure(
        source_extensions=frozenset(_strings(raw, "source_extensions", "[measure]")),
        source_names=frozenset(_strings(raw, "source_names", "[measure]")),
        entry_files=_strings(raw, "entry_files", "[measure]"),
        module_roots=_strings(raw, "module_roots", "[measure]"),
        banned_directory_names=frozenset(_strings(raw, "banned_directory_names", "[measure]")),
    )


def load_config(path: Path = CONFIG_PATH) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{path}: {error}") from error
    migrations = _table(raw, "migrations")
    return Config(
        limits=_limits(_table(raw, "limits")),
        measure=_measure(_table(raw, "measure")),
        unmeasured=_entries(raw, "unmeasured", with_rules=False),
        exceptions=_entries(raw, "exceptions", with_rules=True),
        protected_migrations=_strings(migrations, "protected", "[migrations]"),
        allowed_migration_changes=_entries(migrations, "allowed_changes", with_rules=False),
    )
