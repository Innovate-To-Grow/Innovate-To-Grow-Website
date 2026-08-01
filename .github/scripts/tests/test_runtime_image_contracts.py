from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class RuntimeImageContractTests(unittest.TestCase):
    def test_python_runtime_images_remove_build_tooling(self) -> None:
        for relative_path in ("src/Dockerfile", "archive/page/Dockerfile"):
            with self.subTest(dockerfile=relative_path):
                dockerfile = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
                production_stage = dockerfile.split("\nFROM ", maxsplit=2)[-1]
                uninstall = "python -m pip uninstall --yes setuptools wheel pip"

                self.assertIn(uninstall, production_stage)
                self.assertLess(production_stage.index(uninstall), production_stage.index("USER app"))


if __name__ == "__main__":
    unittest.main()
