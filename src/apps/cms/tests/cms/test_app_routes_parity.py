"""Cross-check that the backend app-route registry stays in sync with the
frontend `EMBED_APP_ROUTE_COMPONENTS` map and the route-scoped section presets.

These registries live in three independent files that all encode the same
route strings; failing CI here means a route was added/renamed in one place
without the others.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.cms.app_routes import (
    EMBEDDABLE_APP_ROUTES,
    PROTECTED_APP_ROUTES,
    PUBLIC_APP_ROUTE_PATTERNS,
    PUBLIC_APP_ROUTES,
    SCHEDULE_SELECTABLE_APP_ROUTES,
)
from apps.cms.services.embed.embed_sections import ROUTE_HIDDEN_SECTION_PRESETS

EMBED_REGISTRY_PATH = (
    Path(settings.BASE_DIR).parent / "pages" / "src" / "features" / "cms" / "components" / "embedAppRoutes.ts"
)

# Matches lines like "  '/schedule': React.lazy(...)" inside the registry object.
# Accepts both single and double quotes so the test stays stable across
# Prettier configs and hand-edits.
_ROUTE_KEY_RE = re.compile(r"""^\s*['"](/[\w-]+)['"]:\s*React\.lazy""", flags=re.MULTILINE)
# Matches "SCHEDULE_SELECTABLE_EMBED_ROUTES ... = new Set(['/schedule', ...])".
_SCHEDULE_ROUTES_RE = re.compile(r"SCHEDULE_SELECTABLE_EMBED_ROUTES[^=]*=\s*new Set\(\[(.*?)\]\)", flags=re.S)
_ROUTER_PATH_RE = re.compile(r"""\{\s*path:\s*['"]([^'"]+)['"]""")


def _frontend_embed_routes() -> set[str]:
    source = EMBED_REGISTRY_PATH.read_text(encoding="utf-8")
    return set(_ROUTE_KEY_RE.findall(source))


class AppRoutesParityTests(SimpleTestCase):
    def test_public_route_conflict_registry_matches_frontend_router(self):
        source = (Path(settings.BASE_DIR).parent / "pages" / "src" / "app" / "router" / "router.tsx").read_text(
            encoding="utf-8"
        )
        frontend_routes = {
            value if value.startswith("/") else f"/{value}"
            for value in _ROUTER_PATH_RE.findall(source)
            if value not in {"/", "*"}
        }
        backend_routes = {
            *(entry["url"] for entry in PUBLIC_APP_ROUTES),
            *PUBLIC_APP_ROUTE_PATTERNS,
            *PROTECTED_APP_ROUTES,
        }
        self.assertEqual(
            backend_routes,
            frontend_routes,
            "Public/protected backend route registries drifted from pages/src/app/router.tsx.",
        )

    def test_embed_app_route_components_match_embeddable_routes(self):
        backend = {r["url"] for r in EMBEDDABLE_APP_ROUTES}
        frontend = _frontend_embed_routes()
        self.assertTrue(frontend, f"No route keys parsed from {EMBED_REGISTRY_PATH}")
        self.assertEqual(
            backend,
            frontend,
            "Backend EMBEDDABLE_APP_ROUTES and frontend EMBED_APP_ROUTE_COMPONENTS drifted. "
            f"Backend-only: {sorted(backend - frontend)}; frontend-only: {sorted(frontend - backend)}.",
        )

    def test_schedule_selectable_routes_match_frontend_registry(self):
        source = EMBED_REGISTRY_PATH.read_text(encoding="utf-8")
        match = _SCHEDULE_ROUTES_RE.search(source)
        self.assertIsNotNone(match, f"SCHEDULE_SELECTABLE_EMBED_ROUTES not found in {EMBED_REGISTRY_PATH}")
        frontend = set(re.findall(r"""['"](/[\w-]+)['"]""", match.group(1)))
        self.assertEqual(
            SCHEDULE_SELECTABLE_APP_ROUTES,
            frontend,
            "Backend schedule_selectable routes and frontend SCHEDULE_SELECTABLE_EMBED_ROUTES drifted.",
        )
        self.assertTrue(SCHEDULE_SELECTABLE_APP_ROUTES <= {r["url"] for r in EMBEDDABLE_APP_ROUTES})

    def test_route_supports_schedule_helpers(self):
        from types import SimpleNamespace

        from apps.cms.app_routes import route_supports_schedule, widget_supports_schedule

        self.assertTrue(route_supports_schedule("/schedule"))
        self.assertTrue(route_supports_schedule(" /schedule "))
        self.assertFalse(route_supports_schedule("/news"))
        self.assertFalse(route_supports_schedule(""))
        self.assertFalse(route_supports_schedule(None))
        self.assertTrue(widget_supports_schedule(SimpleNamespace(widget_type="app_route", app_route="/schedule")))
        self.assertFalse(widget_supports_schedule(SimpleNamespace(widget_type="blocks", app_route="/schedule")))
        self.assertFalse(widget_supports_schedule(SimpleNamespace(widget_type="app_route", app_route="/news")))

    def test_route_hidden_section_presets_keys_are_embeddable(self):
        backend = {r["url"] for r in EMBEDDABLE_APP_ROUTES}
        preset_keys = set(ROUTE_HIDDEN_SECTION_PRESETS)
        invalid = preset_keys - backend
        self.assertEqual(
            invalid,
            set(),
            f"ROUTE_HIDDEN_SECTION_PRESETS keys not in EMBEDDABLE_APP_ROUTES: {sorted(invalid)}",
        )
