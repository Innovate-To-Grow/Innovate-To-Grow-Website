"""``config.settings.base.framework.environment`` loads ``src/.env`` through python-dotenv at import.

The module is re-imported with the real ``dotenv.load_dotenv`` pointed at a temporary file (never the
developer's own ``src/.env``), so the parser and the defaults our call relies on are what is tested.
"""

import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import dotenv
from django.test import SimpleTestCase

ENVIRONMENT_MODULE = "config.settings.base.framework.environment"


class EnvironmentDotenvTests(SimpleTestCase):
    def setUp(self):
        self.module = importlib.import_module(ENVIRONMENT_MODULE)
        self.addCleanup(importlib.reload, self.module)  # back to the values the test process started with
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env_file = Path(tmp.name) / ".env"

    def reload_with(self, dotenv_text, **process_env):
        """Re-import the module with ``dotenv_text`` as ``src/.env``; return it and the paths it asked for."""
        self.env_file.write_text(dotenv_text, encoding="utf-8")
        real_load_dotenv = dotenv.load_dotenv
        requested = []

        def load_temporary_file(dotenv_path, **kwargs):
            requested.append(Path(dotenv_path))
            return real_load_dotenv(self.env_file, **kwargs)

        with (
            patch.dict(os.environ, process_env, clear=True),
            patch("dotenv.load_dotenv", side_effect=load_temporary_file),
        ):
            module = importlib.reload(self.module)
        return module, requested

    def test_reads_the_env_file_in_the_src_directory(self):
        module, requested = self.reload_with('FRONTEND_URL="https://from-dotenv.example"\nLEGACY_VIEW_ENABLED=true\n')

        self.assertEqual(requested, [module.BASE_DIR / ".env"])
        self.assertEqual(module.BASE_DIR, Path(__file__).resolve().parents[4])
        self.assertEqual(module.FRONTEND_URL, "https://from-dotenv.example")
        self.assertTrue(module.LEGACY_VIEW_ENABLED)

    def test_process_environment_wins_over_the_env_file(self):
        # ECS injects production values; a stale .env must never override them.
        module, _ = self.reload_with(
            "BACKEND_URL=https://from-dotenv.example\nAMPLIFY_APP_ID=from-dotenv\n",
            BACKEND_URL="https://from-ecs.example",
        )

        self.assertEqual(module.BACKEND_URL, "https://from-ecs.example")
        self.assertEqual(module.AMPLIFY_APP_ID, "from-dotenv")

    def test_blank_value_with_inline_comment_stays_blank(self):
        # python-dotenv 1.2.4+: ``KEY= # note`` is empty, not the comment text, so an optional SES
        # configuration set left blank this way is not sent to SES as "# note".
        module, _ = self.reload_with(
            "SES_CONFIGURATION_SET_NAME= # optional\nBACKGROUND_JOB_METRICS_NAMESPACE=  # optional\n"
        )

        self.assertEqual(module.SES_CONFIGURATION_SET_NAME, "")
        self.assertEqual(module.BACKGROUND_JOB_METRICS_NAMESPACE, "")
