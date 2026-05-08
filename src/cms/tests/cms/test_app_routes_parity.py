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

from cms.app_routes import EMBEDDABLE_APP_ROUTES
from cms.embed_sections import ROUTE_HIDDEN_SECTION_PRESETS

EMBED_REGISTRY_PATH = Path(settings.BASE_DIR).parent / "pages" / "src" / "components" / "CMS" / "embedAppRoutes.ts"

# Matches lines like "  '/schedule': React.lazy(...)" inside the registry object.
# Accepts both single and double quotes so the test stays stable across
# Prettier configs and hand-edits.
_ROUTE_KEY_RE = re.compile(r"""^\s*['"](/[\w-]+)['"]:\s*React\.lazy""", flags=re.MULTILINE)


def _frontend_embed_routes() -> set[str]:
    source = EMBED_REGISTRY_PATH.read_text(encoding="utf-8")
    return set(_ROUTE_KEY_RE.findall(source))


class AppRoutesParityTests(SimpleTestCase):
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

    def test_route_hidden_section_presets_keys_are_embeddable(self):
        backend = {r["url"] for r in EMBEDDABLE_APP_ROUTES}
        preset_keys = set(ROUTE_HIDDEN_SECTION_PRESETS)
        invalid = preset_keys - backend
        self.assertEqual(
            invalid,
            set(),
            f"ROUTE_HIDDEN_SECTION_PRESETS keys not in EMBEDDABLE_APP_ROUTES: {sorted(invalid)}",
        )
