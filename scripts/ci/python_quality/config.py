from __future__ import annotations

import fnmatch
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


CONFIG_PATH = ROOT / "scripts" / "ci" / "python_quality" / "python_quality.toml"


@dataclass
class Profile:
    """Thresholds for one class of files; ``None`` disables a metric."""

    name: str
    file_lines: tuple[int, int] | None = None
    function_lines: tuple[int, int] | None = None
    nesting: tuple[int, int] | None = None
    complexity: tuple[int, int] | None = None
    patterns: list[str] = field(default_factory=list)


@dataclass
class Config:
    roots: list[str]
    exclude: list[str]
    profiles: list[Profile]
    directory_files: tuple[int, int]
    exceptions: dict[str, str]

    def profile_for(self, rel: str) -> Profile:
        for profile in self.profiles:
            if _matches(rel, profile.patterns):
                return profile
        return self.profiles[-1]

    def is_excluded(self, rel: str) -> bool:
        return _matches(rel, self.exclude)


def _matches(rel: str, patterns: Iterable[str]) -> bool:
    """fnmatch-style match (``*`` also crosses ``/``), like Bandit's exclude_dirs."""
    return any(fnmatch.fnmatchcase(rel, pattern) for pattern in patterns)


def _pair(raw: dict, key: str) -> tuple[int, int] | None:
    value = raw.get(key)
    return None if value is None else (int(value[0]), int(value[1]))


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    profiles = [
        Profile(
            name=name,
            patterns=list(body.get("patterns", [])),
            file_lines=_pair(body, "file_lines"),
            function_lines=_pair(body, "function_lines"),
            nesting=_pair(body, "nesting"),
            complexity=_pair(body, "complexity"),
        )
        for name, body in raw["profiles"].items()
    ]
    exceptions = {entry["key"]: entry["reason"] for entry in raw.get("exceptions", [])}
    return Config(
        roots=list(raw["roots"]),
        exclude=list(raw.get("exclude", [])),
        profiles=profiles,
        directory_files=_pair(raw, "directory_files") or (15, 25),
        exceptions=exceptions,
    )
