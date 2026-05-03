import asyncio

from django.test import SimpleTestCase

from core.admin.system_intelligence.adk_web import SystemIntelligenceADKRouter

from .adk_web_helpers import RecorderApp, invoke_http


class SystemIntelligenceADKRouterTests(SimpleTestCase):
    def test_router_strips_adk_prefix_before_forwarding(self):
        django_app = RecorderApp()
        adk_app = RecorderApp()
        app = SystemIntelligenceADKRouter(django_app, adk_app)

        asyncio.run(invoke_http(app, {"path": "/admin/core/system-intelligence/adk/dev-ui/"}))

        self.assertEqual(adk_app.scope["root_path"], "")
        self.assertEqual(adk_app.scope["path"], "/dev-ui/")
        self.assertIsNone(django_app.scope)
