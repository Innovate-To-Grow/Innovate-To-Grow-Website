from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

from scripts.ci.validate_tool_versions import PIN_GROUPS, PinError, Regex, collect_pins, main, mismatches

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

CI = ".github/workflows/ci.yml"
DEPENDENCY_AUDIT = ".github/workflows/dependency-audit.yml"
BAKE_IMAGE = "aws/ci-runners/bake-image.sh"
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
      - run: pip install "pip-audit[cyclonedx]==2.7.3"
      - run: pip-audit --ignore-vuln GHSA-aaaa-bbbb-cccc --ignore-vuln PYSEC-2026-1
  backend-docker-smoke:
    steps:
      - run: postgres_image="postgres:16"
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
  - run: pip install "pip-audit[cyclonedx]==2.7.3"
  # Keep the --ignore-vuln list in sync with the python-dependency-audit job in ci.yml.
  - run: pip-audit --ignore-vuln PYSEC-2026-1 --ignore-vuln GHSA-aaaa-bbbb-cccc
""",
    ".github/workflows/deploy-backend.yml": 'steps:\n  - with:\n      python-version: "3.14"\n',
    ".github/workflows/deploy-archive.yml": 'steps:\n  - with:\n      python-version: "3.14"\n',
    ".github/workflows/deploy-frontend.yml": """\
steps:
  - with:
      python-version: "3.14"
  - with:
      node-version: "22.22.2"
""",
    ".github/workflows/aws-runner-smoke.yml": """\
jobs:
  verify:
    services:
      postgres:
        image: postgres:16
    steps:
      - with:
          python-version: "3.14"
      - with:
          node-version: "22.22.2"
      - run: docker image inspect <image> >/dev/null
""",
    BAKE_IMAGE: """\
curl -fsSL https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.xz -o node.tar.xz
curl -fsSL https://nodejs.org/dist/v22.22.2/SHASUMS256.txt -o node-shasums.txt
expected=$(awk '$2 == "node-v22.22.2-linux-x64.tar.xz" { print $1 }' node-shasums.txt)
mkdir -p "$RUNNER_TOOL_CACHE/node/22.22.2/x64"
tar -xJf node.tar.xz --strip-components=1 -C "$RUNNER_TOOL_CACHE/node/22.22.2/x64"
touch "$RUNNER_TOOL_CACHE/node/22.22.2/x64.complete"
ln -sf "$RUNNER_TOOL_CACHE/node/22.22.2/x64/bin/"* /usr/local/bin/
for version in 3.11.18 3.14.10; do
  echo "$version"
done
docker pull postgres:16
docker pull <image>
""",
    "aws/ci-runners/image.tf": """\
inputs = { commands = [
  "node --version | grep '^v22.22.2$'",
] }
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
    "playwright-image": (IMAGE, 3),
    "playwright": ("1.64.0", 3),
    "node": ("22.22.2", 6),
    "python-backend": ("3.14", 6),
    "python-tooling": ("3.11", 4),
    "postgres": ("16", 3),
    "pip-audit": ("2.7.3", 2),
    "pip-audit-ignores": (IGNORED, 2),
}

# (group, file, old text, new text, aligned value, drifted value): each edit moves exactly one source.
DRIFTS = (
    ("ruff", PRE_COMMIT, "rev: v0.17.2", "rev: v0.18.0", "0.17.2", "0.18.0"),
    ("ruff", "src/requirements/local.txt", "ruff==0.17.2", "ruff==0.18.0", "0.17.2", "0.18.0"),
    ("bandit", PRE_COMMIT, "bandit[toml]==1.7.10", "bandit[toml]==1.8.0", "1.7.10", "1.8.0"),
    ("gitleaks", "scripts/pre-commit/gitleaks-protect.sh", ":-8.21.2", ":-8.22.0", "8.21.2", "8.22.0"),
    ("playwright-image", BAKE_IMAGE, DIGEST, "f" * 64, IMAGE, IMAGE.replace(DIGEST, "f" * 64)),
    ("playwright", CI, "pw-v1.64.0-noble", "pw-v1.62.1-noble", "1.64.0", "1.62.1"),
    ("playwright", PACKAGE_LOCK, '"version": "1.64.0"', '"version": "1.65.0"', "1.64.0", "1.65.0"),
    ("node", "aws/ci-runners/image.tf", "^v22.22.2$", "^v22.22.3$", "22.22.2", "22.22.3"),
    ("node", BAKE_IMAGE, "node/22.22.2/x64.complete", "node/22.22.3/x64.complete", "22.22.2", "22.22.3"),
    ("python-backend", BAKE_IMAGE, "3.11.18 3.14.10", "3.11.18 3.15.0", "3.14", "3.15"),
    ("python-backend", ".github/workflows/deploy-archive.yml", '"3.14"', '"3.13"', "3.14", "3.13"),
    ("python-tooling", ".github/workflows/lint.yml", '"3.11"', '"3.12"', "3.11", "3.12"),
    ("python-tooling", BAKE_IMAGE, "3.11.18 3.14.10", "3.12.9 3.14.10", "3.11", "3.12"),
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


class CollectPinsTests(unittest.TestCase):
    def test_aligned_fixture_reads_every_group_without_mismatches(self) -> None:
        with fake_repository() as root:
            pins = collect_pins(root)

        self.assertEqual(list(pins), list(EXPECTED))
        for group, (value, sources) in EXPECTED.items():
            with self.subTest(group=group):
                self.assertEqual([pin_value for _, pin_value in pins[group]], [value] * sources)
        self.assertEqual(mismatches(pins), [])

    def test_each_drift_is_reported_for_its_group_only(self) -> None:
        for group, path, old, new, aligned, drifted in DRIFTS:
            with self.subTest(group=group, path=path), fake_repository() as root:
                replace_once(root, path, old, new)

                problems = mismatches(collect_pins(root))

                self.assertEqual([problem.split(":")[0] for problem in problems], [group], problems)
                self.assertIn(f"{drifted} ({path}", problems[0])
                self.assertIn(f"{aligned} (", problems[0])

    def test_labels_name_the_lines_each_value_was_found_on(self) -> None:
        with fake_repository() as root:
            replace_once(root, CI, "postgres:16", "postgres:17")
            lines = (root / CI).read_text(encoding="utf-8").splitlines()
            (problem,) = mismatches(collect_pins(root))

        def lines_with(text: str) -> str:
            return ",".join(str(number) for number, line in enumerate(lines, 1) if text in line)

        self.assertTrue(problem.startswith(f"postgres: 17 ({CI}:{lines_with('postgres:17')}) vs 16 ({CI}:"), problem)
        self.assertIn(f"{CI}:{lines_with('postgres:16')}, ", problem)

    def test_a_source_that_finds_nothing_names_its_file_and_target(self) -> None:
        cases = (
            ("scripts/pre-commit/gitleaks-protect.sh", "${GITLEAKS_VERSION:-8.21.2}", "8.21.2", "GITLEAKS_VERSION"),
            # Only literals are pins: a `${{ env.* }}` expression leaves the file without one.
            (
                ".github/workflows/deploy-frontend.yml",
                'node-version: "22.22.2"',
                "node-version: ${{ env.NODE_VERSION }}",
                "node-version",
            ),
            # A third baked interpreter breaks the tooling/backend split by position.
            (BAKE_IMAGE, "3.11.18 3.14.10", "3.11.18 3.12.9 3.14.10", "for version in"),
            (PRE_COMMIT, "astral-sh/ruff-pre-commit", "charliermarsh/ruff-pre-commit", "astral-sh/ruff-pre-commit"),
            (PRE_COMMIT, '"bandit[toml]==1.7.10"', '"bandit[toml]"', "bandit"),
            (PACKAGE_LOCK, '"node_modules/@playwright/test"', '"node_modules/playwright"', "@playwright/test"),
        )
        for path, old, new, looked_for in cases:
            with self.subTest(path=path, looked_for=looked_for), fake_repository() as root:
                replace_once(root, path, old, new)

                with self.assertRaises(PinError) as caught:
                    collect_pins(root)

                self.assertTrue(str(caught.exception).startswith(f"{path}: "), caught.exception)
                self.assertIn(looked_for, str(caught.exception))

    def test_fewer_matches_than_the_minimum_is_a_pin_error(self) -> None:
        cases = (
            (CI, "image: postgres:16", "image: postgres:latest", "postgres", "found 3"),
            (CI, f'"{IMAGE}"', '"mcr.microsoft.com/playwright:v1.64.0-noble"', "sha256", "found 1"),
            (CI, '"pip-audit[cyclonedx]==2.7.3"', "pip-audit", "pip-audit", "found 0"),
            (BAKE_IMAGE, "$RUNNER_TOOL_CACHE/node/22.22.2/x64/bin/", "$NODE_HOME/bin/", "node", "found 7"),
        )
        for path, old, new, looked_for, found in cases:
            with self.subTest(path=path, looked_for=looked_for), fake_repository() as root:
                replace_once(root, path, old, new)

                with self.assertRaises(PinError) as caught:
                    collect_pins(root)

                message = str(caught.exception)
                self.assertTrue(message.startswith(f"{path}: expected at least "), message)
                self.assertIn(looked_for, message)
                self.assertTrue(message.endswith(found), message)

    def test_a_missing_file_is_a_pin_error(self) -> None:
        with fake_repository() as root:
            (root / ".github/workflows/deploy-archive.yml").unlink()

            with self.assertRaisesRegex(PinError, r"^\.github/workflows/deploy-archive\.yml: cannot read"):
                collect_pins(root)

    def test_each_repository_source_declares_its_exact_match_count(self) -> None:
        # A minimum below the real count lets one occurrence be rewritten (say to
        # postgres:latest) and silently drop out of the check while the rest still
        # agree. Keeping each minimum equal to the count closes that gap.
        for group, sources in PIN_GROUPS.items():
            for source in sources:
                if not isinstance(source, Regex) or source.as_set:
                    continue
                with self.subTest(group=group, path=source.path, regex=source.regex):
                    text = (REPOSITORY_ROOT / source.path).read_text(encoding="utf-8")
                    self.assertEqual(len(re.findall(source.regex, text, re.MULTILINE)), source.minimum)


class MainTests(unittest.TestCase):
    def run_main(self, root: Path) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--root", str(root)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_aligned_checkout_prints_one_summary_line(self) -> None:
        with fake_repository() as root:
            code, stdout, stderr = self.run_main(root)

        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(stdout.count("\n"), 1)
        self.assertTrue(stdout.startswith("Tool versions aligned: ruff=0.17.2, bandit=1.7.10, gitleaks=8.21.2, "))
        self.assertIn(f", pip-audit-ignores={IGNORED}\n", stdout)

    def test_drift_fails_naming_the_group_and_both_values(self) -> None:
        with fake_repository() as root:
            replace_once(root, CI, "pw-v1.64.0-noble", "pw-v1.62.1-noble")
            code, stdout, stderr = self.run_main(root)

        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("playwright: 1.64.0 (", stderr)
        self.assertIn(f" vs 1.62.1 ({CI}:", stderr)

    def test_pin_error_fails_with_its_message(self) -> None:
        with fake_repository() as root:
            (root / PACKAGE_LOCK).unlink()
            code, stdout, stderr = self.run_main(root)

        self.assertEqual((code, stdout), (1, ""))
        self.assertIn(f"{PACKAGE_LOCK}: cannot read", stderr)


class RepositoryPinsTests(unittest.TestCase):
    def test_repository_pins_are_aligned(self) -> None:
        self.assertEqual(mismatches(collect_pins(REPOSITORY_ROOT)), [])


if __name__ == "__main__":
    unittest.main()
