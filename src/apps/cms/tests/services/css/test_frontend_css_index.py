from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.audit import (
    default_frontend_dir,
    frontend_css_index,
)
from apps.cms.tests.services.css_audit.test_css_audit import EMPTY_MAPS, ENTRY_AND_ROUTE_FRONTEND, make_frontend_dir


class FrontendCssIndexTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_without_main_tsx_every_file_counts_as_entry(self):
        root = make_frontend_dir(
            self,
            {
                "features/a/One.css": ".shared {}\n.only-a {}",
                "app/Two.css": ".shared:hover {}",
                "features/a/One.tsx": "const x = '.not-css';",
            },
        )

        index = frontend_css_index(root)

        self.assertEqual(set(index), {"defined", "scoped", "hook", "route", "graph"})
        self.assertFalse(index["graph"])
        self.assertEqual(
            dict(index["defined"]), {"shared": {"features/a/One.css", "app/Two.css"}, "only-a": {"features/a/One.css"}}
        )
        self.assertEqual((dict(index["route"]), dict(index["scoped"]), dict(index["hook"])), ({}, {}, {}))

    def test_main_tsx_splits_entry_and_route_files(self):
        root = make_frontend_dir(self, ENTRY_AND_ROUTE_FRONTEND)

        index = frontend_css_index(root)

        self.assertTrue(index["graph"])
        self.assertEqual(dict(index["defined"]), {"in-frontend": {"index.css"}})
        self.assertEqual(dict(index["route"]), {"route-only": {"routes/Lazy.css"}})
        # Scoped and hook classes are listed whichever bundle the file lands in.
        self.assertEqual(dict(index["scoped"]), {"route-scoped": {"routes/Lazy.css"}})
        self.assertEqual(dict(index["hook"]), {"lazy-page": {"routes/Lazy.css"}})

    def test_css_reached_statically_and_lazily_is_in_the_entry_bundle(self):
        root = make_frontend_dir(
            self,
            {
                **ENTRY_AND_ROUTE_FRONTEND,
                "App.tsx": (
                    "import './shared.css';\n"
                    "const Lazy = React.lazy(() => import('./routes/Lazy'));\nexport const App = () => null;\n"
                ),
                "routes/Lazy.tsx": "import '../shared.css';\nimport './Lazy.css';\nexport default () => null;\n",
                "shared.css": ".both-ways {}",
            },
        )

        index = frontend_css_index(root)

        self.assertEqual(dict(index["defined"]), {"in-frontend": {"index.css"}, "both-ways": {"shared.css"}})
        self.assertEqual(dict(index["route"]), {"route-only": {"routes/Lazy.css"}})

    def test_scoped_and_hook_classes_are_indexed_per_file(self):
        root = make_frontend_dir(
            self,
            {
                "pages/Event.css": ".event-page .lead {}\n.event-page {}",
                "pages/News.css": ".news .lead {}",
                "base.css": ".lead {}",
            },
        )

        index = frontend_css_index(root)

        self.assertEqual(dict(index["defined"]), {"event-page": {"pages/Event.css"}, "lead": {"base.css"}})
        self.assertEqual(dict(index["scoped"]), {"lead": {"pages/Event.css", "pages/News.css"}})
        # A file that defines a class is not listed as hooking on it.
        self.assertEqual(dict(index["hook"]), {"news": {"pages/News.css"}})

    def test_dependency_build_and_test_dirs_are_not_indexed(self):
        root = make_frontend_dir(
            self,
            {
                "kept.css": ".kept {}",
                "node_modules/pkg/x.css": ".pkg {}",
                "dist/assets/index.css": ".built {}",
                "__tests__/fixture.css": ".fixture {}",
            },
        )
        self.assertEqual(dict(frontend_css_index(root)["defined"]), {"kept": {"kept.css"}})

    def test_accepts_string_path(self):
        root = make_frontend_dir(self, {"x.css": ".x {}"})
        self.assertEqual(dict(frontend_css_index(str(root))["defined"]), {"x": {"x.css"}})

    def test_missing_dir_returns_empty(self):
        missing = make_frontend_dir(self, {}) / "no-such-frontend"

        self.assertEqual(frontend_css_index(missing), {**EMPTY_MAPS, "route": {}, "graph": False})

    def test_default_frontend_dir_is_pages_src(self):
        self.assertEqual(default_frontend_dir(), Path(settings.BASE_DIR).parent / "pages" / "src")

    def test_default_dir_is_scanned_through_its_import_graph(self):
        index = frontend_css_index()

        self.assertTrue(index["graph"])
        self.assertEqual(index["defined"]["maintenance-container"], {"app/MaintenanceMode/MaintenanceMode.css"})
        # SheetsDataTable is only reached through a lazily loaded route.
        self.assertNotIn("sdt-search", index["defined"])
        self.assertEqual(index["route"]["sdt-search"], {"components/SheetsDataTable/SheetsDataTable.css"})
