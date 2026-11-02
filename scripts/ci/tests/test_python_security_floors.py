"""Backend Python security floors reach every install path (no network needed).

Trivy scans the backend image (``src/Dockerfile``) and pip-audit the CI closure
(``src/requirements.txt``). Both read the manifests under ``src/requirements/``
through ``-r`` includes, so a floor only protects the install paths whose include
closure contains it.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
DOCKERFILE = SRC / "Dockerfile"
# Installed by the Django CI suites; also what pip-audit and the SBOM resolve.
CI_REQUIREMENTS = SRC / "requirements.txt"

# Code-scanning alert #657 (CVE-2026-112940, GHSA-v4x8-3wr5-3wq8): filelock's
# ReadWriteLock is affected from 3.20.4 and fixed in 4.2.1; the image shipped 3.32.7.
FILELOCK_FIXED = (4, 2, 1)

_COMMENT = re.compile(r"(^|\s)#.*$")
_INCLUDE = re.compile(r"^(?:-r|--requirement|-c|--constraint)(?:\s*=\s*|\s+|(?=\S))(?P<path>\S+)$")
_LINE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?P<spec>[^;]*)(?P<marker>;.*)?$")
_CLAUSE = re.compile(r"^(?P<op>~=|==|!=|<=|>=|<|>)\s*(?P<version>\d+(?:\.\d+)*)$")
_LOWER_BOUNDS = {"~=", "==", ">=", ">"}


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _release(version: str) -> tuple[int, ...]:
    """Release segment with trailing zeros dropped, so ``4.2`` and ``4.2.0`` compare equal."""
    parts = [int(part) for part in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def requirement_lines(path: Path, seen: set[Path] | None = None) -> list[str]:
    """Requirement lines of ``path`` and every file it includes, resolved like pip (relative to the includer)."""
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _COMMENT.sub("", raw).strip()
        include = _INCLUDE.match(line)
        if include:
            lines.extend(requirement_lines(path.parent / include["path"], seen))
        elif line and not line.startswith("-"):
            lines.append(line)
    return lines


def minimum_version(entrypoint: Path, package: str) -> tuple[int, ...] | None:
    """Lowest release of ``package`` that installing ``entrypoint`` may resolve; None when unbounded."""
    floors: list[tuple[int, ...]] = []
    for line in requirement_lines(entrypoint):
        match = _LINE.match(line)
        # A marker-gated clause does not hold on every interpreter, so it is no floor.
        if not match or match["marker"] or _canonical(match["name"]) != _canonical(package):
            continue
        for clause in filter(None, (part.strip() for part in match["spec"].split(","))):
            parsed = _CLAUSE.match(clause)
            if parsed is None:
                raise ValueError(f"{package}: unsupported specifier {clause!r} in {line!r}")
            if parsed["op"] in _LOWER_BOUNDS:
                floors.append(_release(parsed["version"]))
    return max(floors, default=None)


def docker_install_entrypoints() -> list[Path]:
    """Requirement files the image's ``pip install -r`` steps read (relative to the ``src/`` build context)."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    return [SRC / name for name in re.findall(r"\bpip install\b[^\n]*?\s-r\s+(\S+)", dockerfile)]


class FilelockSecurityFloorTests(unittest.TestCase):
    def test_image_installs_requirements_from_the_build_context(self):
        # Guards the next test against silently checking no image install path.
        entrypoints = docker_install_entrypoints()
        self.assertTrue(entrypoints, "no `pip install -r` found in src/Dockerfile")
        for entrypoint in entrypoints:
            with self.subTest(entrypoint=str(entrypoint.relative_to(ROOT))):
                self.assertTrue(entrypoint.is_file())

    def test_every_backend_install_path_excludes_vulnerable_filelock(self):
        for entrypoint in [*docker_install_entrypoints(), CI_REQUIREMENTS]:
            with self.subTest(entrypoint=str(entrypoint.relative_to(ROOT))):
                minimum = minimum_version(entrypoint, "filelock")
                self.assertIsNotNone(minimum, "filelock has no lower bound, so a vulnerable release can resolve")
                self.assertGreaterEqual(minimum, FILELOCK_FIXED)


class MinimumVersionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_follows_nested_includes_relative_to_each_file(self):
        self.write("requirements/base.txt", "litellm>=1.103.2,<1.104  # capped\nFileLock >= 4.2.1\n")
        self.write("requirements/production.txt", "-r base.txt\n")
        entrypoint = self.write("requirements.txt", "-r requirements/production.txt\n")
        self.assertEqual(minimum_version(entrypoint, "filelock"), (4, 2, 1))

    def test_tightest_floor_wins_across_files_and_constraints(self):
        self.write("constraints.txt", "filelock>=4.2.1\n")
        entrypoint = self.write("requirements.txt", "--constraint=constraints.txt\nfilelock<5,>=3.16.1\n")
        self.assertEqual(minimum_version(entrypoint, "filelock"), (4, 2, 1))

    def test_missing_or_insufficient_floors_are_detected(self):
        cases = {
            "huggingface-hub>=0.34.0\n": None,
            "# filelock>=4.2.1\n": None,
            "filelock<4.0,>=3.16.1\n": (3, 16, 1),
            "filelock>4.2.0\n": (4, 2),  # admits 4.2.0.1, which is still vulnerable
            "filelock>=4.2.1; python_version >= '3.14'\n": None,
        }
        for content, expected in cases.items():
            with self.subTest(content=content):
                self.assertEqual(minimum_version(self.write("requirements.txt", content), "filelock"), expected)

    def test_unsupported_specifier_fails_closed(self):
        with self.assertRaises(ValueError):
            minimum_version(self.write("requirements.txt", "filelock==4.*\n"), "filelock")

    def test_include_cycles_terminate(self):
        self.write("a.txt", "-r b.txt\nfilelock>=4.2.1\n")
        entrypoint = self.write("b.txt", "-ra.txt\n")
        self.assertEqual(minimum_version(entrypoint, "filelock"), (4, 2, 1))


if __name__ == "__main__":
    unittest.main()
