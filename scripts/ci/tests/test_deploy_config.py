import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.deploy.load_config import export_config


class DeploymentConfigTests(unittest.TestCase):
    def test_rejects_environment_injection_before_writing(self):
        for config in ({"NODE_OPTIONS": "--require=/tmp/evil"}, {"DB_HOST": "good\nPATH=/tmp"}, {"DB_PORT": 5432}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "env"
                with self.assertRaises(ValueError):
                    export_config(config, path)
                self.assertFalse(path.exists())

    def test_exports_values_without_printing_them_or_masking_public_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                export_config({"DB_HOST": "private-db.example", "AWS_REGION": "us-west-2"}, path)
            self.assertEqual(path.read_text(), "DB_HOST=private-db.example\nAWS_REGION=us-west-2\n")
            self.assertNotIn("private-db.example", output.getvalue())
            self.assertNotIn("add-mask", output.getvalue())
