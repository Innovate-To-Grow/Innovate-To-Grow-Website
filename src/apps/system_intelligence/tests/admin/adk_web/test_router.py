import asyncio

from django.test import SimpleTestCase

from apps.system_intelligence.admin.adk_web import SystemIntelligenceADKRouter

from .adk_web_helpers import RecorderApp, invoke_http


class SystemIntelligenceADKRouterTests(SimpleTestCase):
    def test_router_forwards_adk_prefix_with_matching_root_path(self):
        django_app = RecorderApp()
        adk_app = RecorderApp()
        app = SystemIntelligenceADKRouter(django_app, adk_app)

        asyncio.run(invoke_http(app, {"path": "/admin/system-intelligence/adk/dev-ui/"}))

        self.assertEqual(adk_app.scope["root_path"], "/admin/system-intelligence/adk")
        self.assertEqual(adk_app.scope["path"], "/admin/system-intelligence/adk/dev-ui/")
        self.assertIsNone(django_app.scope)
