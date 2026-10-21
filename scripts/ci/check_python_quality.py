#!/usr/bin/env python3
"""Report and enforce size / nesting / complexity limits for active Python code.

Counting rules (documented in docs/architecture/code-quality.md):

* A *logical line* is a physical line holding at least one code token. Blank
  lines, comment-only lines and docstring lines are not counted.
* File length = logical lines in the file.
* Function length = logical lines from the ``def`` line to the last line of the
  body, nested functions included (each nested function is also measured on its
  own). Decorators are not counted.
* Nesting depth = deepest stack of ``if/for/while/try/with/match`` blocks inside
  one function. ``elif`` and ``except``/``else``/``finally`` stay at the depth
  of the statement they belong to; a nested ``def``/``class`` starts again at 0.
* Complexity = Ruff's ``C901`` (mccabe) score, collected by running Ruff.
* Directory size = ``.py`` files directly inside one directory, ``__init__.py``
  excluded.

Each metric has an *advisory* threshold (reported, never fails) and a *hard*
threshold (fails unless the finding is listed in the exceptions file with a
written reason). Stale exceptions — entries that no longer match a finding —
also fail, so the list can only shrink.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import shutil
import subprocess  # nosec B404 - runs the pinned ruff binary with fixed arguments
import sys
import tokenize
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "scripts" / "ci" / "python_quality.toml"

NON_CODE_TOKENS = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}
BLOCK_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.Match)
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


@dataclass(frozen=True)
class Finding:
    metric: str
    path: str
    symbol: str
    value: int
    advisory: int
    hard: int

    @property
    def key(self) -> str:
        return f"{self.metric}:{self.path}::{self.symbol}" if self.symbol else f"{self.metric}:{self.path}"

    @property
    def is_hard(self) -> bool:
        return self.value > self.hard

    def describe(self) -> str:
        level = "HARD" if self.is_hard else "advisory"
        where = f"{self.path}::{self.symbol}" if self.symbol else self.path
        return f"[{level}] {self.metric} {self.value} (advisory>{self.advisory}, hard>{self.hard})  {where}"


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


def docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return lines


def code_lines(source: str, tree: ast.AST) -> set[int]:
    """Physical line numbers that carry code (see module docstring)."""
    skip = docstring_lines(tree)
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in NON_CODE_TOKENS:
            continue
        for line in range(token.start[0], token.end[0] + 1):
            if line not in skip:
                lines.add(line)
    return lines


def _child_blocks(node: ast.AST) -> Iterator[tuple[ast.AST, int]]:
    """Yield (child, depth increment) pairs, flattening ``elif`` chains."""
    for name, value in ast.iter_fields(node):
        children = value if isinstance(value, list) else [value]
        for child in children:
            if not isinstance(child, ast.AST):
                continue
            if isinstance(node, ast.If) and name == "orelse" and len(value) == 1 and isinstance(child, ast.If):
                yield child, 0
            else:
                yield child, 1 if isinstance(child, BLOCK_NODES) else 0


def max_nesting(function: ast.AST) -> int:
    deepest = 0
    stack: list[tuple[ast.AST, int]] = [(child, inc) for child, inc in _child_blocks(function)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, SCOPE_NODES):
            continue
        deepest = max(deepest, depth)
        for child, inc in _child_blocks(node):
            stack.append((child, depth + inc))
    return deepest


def iter_functions(tree: ast.AST) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    def visit(node: ast.AST, prefix: str) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = f"{prefix}{child.name}"
                yield name, child
                yield from visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                yield from visit(child, f"{prefix}{child.name}.")
            else:
                yield from visit(child, prefix)

    yield from visit(tree, "")


def _check(metric: str, rel: str, symbol: str, value: int, limits: tuple[int, int] | None) -> Iterator[Finding]:
    if limits and value > limits[0]:
        yield Finding(metric, rel, symbol, value, limits[0], limits[1])


def analyze_source(rel: str, source: str, profile: Profile) -> list[Finding]:
    tree = ast.parse(source)
    lines = code_lines(source, tree)
    findings = list(_check("file-lines", rel, "", len(lines), profile.file_lines))
    for name, function in iter_functions(tree):
        end = function.end_lineno or function.lineno
        length = sum(1 for line in lines if function.lineno <= line <= end)
        findings.extend(_check("function-lines", rel, name, length, profile.function_lines))
        findings.extend(_check("nesting", rel, name, max_nesting(function), profile.nesting))
    return findings


def iter_python_files(config: Config) -> Iterator[str]:
    for root in config.roots:
        for path in sorted((ROOT / root).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if not config.is_excluded(rel):
                yield rel


def directory_findings(files: Iterable[str], config: Config) -> list[Finding]:
    counts: dict[str, int] = {}
    for rel in files:
        path = Path(rel)
        if path.name != "__init__.py":
            counts[path.parent.as_posix()] = counts.get(path.parent.as_posix(), 0) + 1
    advisory, hard = config.directory_files
    return [
        Finding("directory-files", directory, "", count, advisory, hard)
        for directory, count in sorted(counts.items())
        if count > advisory
    ]


def ruff_complexity(files: list[str], threshold: int) -> dict[tuple[str, str], int]:
    """Return {(path, function): mccabe score} for every function above ``threshold``."""
    ruff = shutil.which("ruff")
    if ruff is None:
        raise SystemExit("ruff is required on PATH to measure complexity (pip install ruff).")
    scores: dict[tuple[str, str], int] = {}
    for start in range(0, len(files), 400):
        chunk = files[start : start + 400]
        completed = subprocess.run(  # nosec B603 - fixed argv, no shell
            [
                ruff,
                "check",
                "--isolated",
                "--select",
                "C901",
                "--config",
                f"lint.mccabe.max-complexity={threshold}",
                "--output-format",
                "json",
                "--exit-zero",
                *chunk,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        for item in json.loads(completed.stdout or "[]"):
            message = item["message"]  # "`name` is too complex (17 > 10)"
            name = message.split("`")[1]
            score = int(message.rsplit("(", 1)[1].split(" ", 1)[0])
            rel = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
            scores[(rel, f"{name}@{item['location']['row']}")] = score
    return scores


def complexity_findings(files: list[str], config: Config) -> list[Finding]:
    by_profile: dict[str, list[str]] = {}
    for rel in files:
        profile = config.profile_for(rel)
        if profile.complexity:
            by_profile.setdefault(profile.name, []).append(rel)
    findings: list[Finding] = []
    for profile in config.profiles:
        if profile.name not in by_profile or not profile.complexity:
            continue
        advisory, hard = profile.complexity
        for (rel, located), score in ruff_complexity(by_profile[profile.name], advisory).items():
            name = located.split("@", 1)[0]
            findings.append(Finding("complexity", rel, name, score, advisory, hard))
    return findings


def collect(config: Config) -> list[Finding]:
    files = list(iter_python_files(config))
    findings: list[Finding] = []
    for rel in files:
        findings.extend(analyze_source(rel, (ROOT / rel).read_text(encoding="utf-8"), config.profile_for(rel)))
    findings.extend(directory_findings(files, config))
    findings.extend(complexity_findings(files, config))
    return sorted(findings, key=lambda finding: (finding.metric, finding.path, finding.symbol))


def evaluate(findings: list[Finding], config: Config) -> tuple[list[Finding], list[str]]:
    """Return (hard findings without an exception, stale exception keys)."""
    hard_keys = {finding.key for finding in findings if finding.is_hard}
    unexcused = [finding for finding in findings if finding.is_hard and finding.key not in config.exceptions]
    stale = sorted(key for key in config.exceptions if key not in hard_keys)
    return unexcused, stale


def summarize(findings: list[Finding]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for finding in findings:
        bucket = summary.setdefault(finding.metric, {"advisory": 0, "hard": 0})
        bucket["hard" if finding.is_hard else "advisory"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write every finding to this JSON file")
    parser.add_argument("--quiet", action="store_true", help="print only the summary and failures")
    args = parser.parse_args(argv)

    config = load_config()
    findings = collect(config)
    unexcused, stale = evaluate(findings, config)

    if not args.quiet:
        for finding in findings:
            excused = " (excepted)" if finding.is_hard and finding.key in config.exceptions else ""
            print(finding.describe() + excused)
    print("\nPython quality summary (advisory / hard):")
    for metric, counts in sorted(summarize(findings).items()):
        print(f"  {metric:16} {counts['advisory']:4} / {counts['hard']:3}")
    if args.json:
        payload = [finding.__dict__ | {"hard_violation": finding.is_hard} for finding in findings]
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for finding in unexcused:
        print(f"ERROR: {finding.describe()}  -> fix it or add `{finding.key}` to {CONFIG_PATH.name}")
    for key in stale:
        print(f"ERROR: stale exception `{key}` no longer exceeds its hard limit; remove it from {CONFIG_PATH.name}")
    return 1 if unexcused or stale else 0


if __name__ == "__main__":
    sys.exit(main())
