from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class RequirementLockContractTests(unittest.TestCase):
    def test_lock_checks_seed_temporary_outputs_from_committed_locks(self) -> None:
        scripts = {
            "backend": (
                REPOSITORY_ROOT / "src/scripts/check-requirements-locks.sh",
                (
                    'cp requirements/production.lock.txt "$tmp_dir/production.lock.txt"',
                    'cp requirements/local.lock.txt "$tmp_dir/local.lock.txt"',
                ),
            ),
            "archive": (
                REPOSITORY_ROOT / "archive/page/check-requirements-locks.sh",
                (
                    'cp requirements.txt "$tmp_dir/requirements.txt"',
                    'cp requirements-dev.txt "$tmp_dir/requirements-dev.txt"',
                ),
            ),
        }

        for name, (path, seed_commands) in scripts.items():
            with self.subTest(name=name):
                script = path.read_text(encoding="utf-8")
                compile_position = script.index("python -m piptools compile")
                for command in seed_commands:
                    self.assertIn(command, script)
                    self.assertLess(script.index(command), compile_position)


if __name__ == "__main__":
    unittest.main()
