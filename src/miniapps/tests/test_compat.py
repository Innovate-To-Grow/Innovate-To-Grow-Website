from django.test import TestCase

from miniapps.compat import get_all_app_routes, get_embeddable_app_routes
from miniapps.models import MiniApp


class CompatBridgeTests(TestCase):
    def test_returns_legacy_plus_db_routes(self):
        routes = get_all_app_routes()
        self.assertGreaterEqual(len(routes), 8)
        urls = [r["url"] for r in routes]
        self.assertIn("/schedule", urls)
        self.assertIn("/current-projects", urls)
        self.assertIn("/news", urls)

    def test_merges_db_apps(self):
        MiniApp.objects.create(url_path="/custom-tool", title="Custom Tool", slug="custom-tool", status="published")
        routes = get_all_app_routes()
        urls = [r["url"] for r in routes]
        self.assertIn("/custom-tool", urls)
        self.assertIn("/schedule", urls)

    def test_db_app_does_not_duplicate_legacy(self):
        MiniApp.objects.create(
            url_path="/schedule", title="Schedule Override", slug="schedule-override", status="published"
        )
        routes = get_all_app_routes()
        schedule_routes = [r for r in routes if r["url"] == "/schedule"]
        self.assertEqual(len(schedule_routes), 1)
        self.assertEqual(schedule_routes[0]["title"], "Event Schedule")

    def test_draft_apps_not_included(self):
        MiniApp.objects.create(url_path="/draft-app", title="Draft", slug="draft-app", status="draft")
        routes = get_all_app_routes()
        urls = [r["url"] for r in routes]
        self.assertNotIn("/draft-app", urls)

    def test_embeddable_filter(self):
        MiniApp.objects.create(
            url_path="/embed-yes", title="Embed", slug="embed-yes", status="published", embeddable=True
        )
        MiniApp.objects.create(
            url_path="/embed-no", title="No Embed", slug="embed-no", status="published", embeddable=False
        )
        routes = get_embeddable_app_routes()
        urls = [r["url"] for r in routes]
        self.assertIn("/embed-yes", urls)
        self.assertNotIn("/embed-no", urls)
        self.assertNotIn("/event", urls)
