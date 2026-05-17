import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from system_intelligence.admin.adk_web.app import get_system_intelligence_adk_asgi_application

from .adk_web_helpers import invoke_http


class SystemIntelligenceADKStaticTests(SimpleTestCase):
    def test_prefixed_dev_ui_static_shell_is_served(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir) / "app"

            with override_settings(BASE_DIR=base_dir, MEDIA_ROOT=base_dir / "media"):
                app = get_system_intelligence_adk_asgi_application()
                messages = asyncio.run(
                    invoke_http(
                        app,
                        {
                            "path": "/admin/system-intelligence/adk/dev-ui/",
                            "root_path": "/admin/system-intelligence/adk",
                        },
                    )
                )

        self.assertEqual(messages[0]["status"], 200)
        self.assertIn(b"<!doctype html>", messages[-1].get("body", b"").lower())
