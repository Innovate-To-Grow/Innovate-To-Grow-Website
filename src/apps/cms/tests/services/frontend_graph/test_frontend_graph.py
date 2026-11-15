"""Tests for ``apps.cms.services.styles.frontend_graph`` (which frontend CSS files the entry bundle loads)."""

import tempfile
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.frontend_graph import (
    ENTRY_MODULE,
    entry_css_files,
)

REAL_FRONTEND_DIR = Path(settings.BASE_DIR).parent / "pages" / "src"


def make_tree(test_case, files):
    """A temp dir holding ``{relative_path: text or bytes}``; returns its ``src`` subdir."""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    root = Path(tmp.name) / "src"
    root.mkdir()
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


class _EntryCssFilesCase(SimpleTestCase):
    def setUp(self):
        cache.clear()


class EntryCssFilesTests(_EntryCssFilesCase):
    def test_without_an_entry_module_returns_none(self):
        self.assertEqual(ENTRY_MODULE, "main.tsx")
        self.assertIsNone(entry_css_files(make_tree(self, {"index.css": ".a {}"})))
        self.assertIsNone(entry_css_files(make_tree(self, {"main.ts": "import './index.css';", "index.css": ""})))
        self.assertIsNone(entry_css_files(make_tree(self, {"main.tsx/index.ts": "import '../index.css';"})))

    def test_entry_without_imports_has_no_css(self):
        self.assertEqual(entry_css_files(make_tree(self, {"main.tsx": "console.log(1);", "x.css": ""})), set())

    def test_side_effect_css_import_from_main(self):
        root = make_tree(self, {"main.tsx": "import './index.css';\n", "index.css": ".a {}", "unused.css": ".b {}"})
        self.assertEqual(entry_css_files(root), {"index.css"})

    def test_accepts_a_string_path(self):
        root = make_tree(self, {"main.tsx": 'import "./index.css"', "index.css": ""})
        self.assertEqual(entry_css_files(str(root)), {"index.css"})

    def test_static_import_forms_are_followed(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "import React from 'react';\n"
                    "import App from './App';\n"
                    "import { a, b } from './named';\n"
                    "import * as ns from './ns';\n"
                    'import Def, { c } from "./def";\n'
                    "import {\n  multi,\n  line,\n} from './multi';\n"
                    "import { type Mixed } from './inline-type';\n"
                ),
                "App.tsx": "import './App.css';",
                "named.ts": "import './named.css';",
                "ns.ts": "import './ns.css';",
                "def.ts": "import './def.css';",
                "multi.ts": "import './multi.css';",
                "inline-type.ts": "import './inline-type.css';",
                "App.css": "",
                "named.css": "",
                "ns.css": "",
                "def.css": "",
                "multi.css": "",
                "inline-type.css": "",
            },
        )

        # An inline ``{ type X }`` still leaves the module import in place, so it is followed.
        self.assertEqual(
            entry_css_files(root),
            {"App.css", "named.css", "ns.css", "def.css", "multi.css", "inline-type.css"},
        )

    def test_imports_without_semicolons_or_on_one_line(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './a.css'\nimport B from './b'\nimport './c.css'; import './d.css';",
                "b.ts": "export default 1",
                "a.css": "",
                "c.css": "",
                "d.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"a.css", "c.css", "d.css"})

    def test_export_from_is_followed(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import { x } from './barrel';",
                "barrel/index.ts": (
                    "export * from './a';\n"
                    "export { b } from './b';\n"
                    "export { default as C } from './c';\n"
                    "export * as ns from './d';\n"
                    "export const local = 'not from here';\n"
                    "export type { T } from './types';\n"
                ),
                "barrel/a.ts": "import './a.css';",
                "barrel/b.ts": "import './b.css';",
                "barrel/c.tsx": "import './c.css';",
                "barrel/d.ts": "import './d.css';",
                "barrel/types.ts": "import './types.css';",
                "barrel/a.css": "",
                "barrel/b.css": "",
                "barrel/c.css": "",
                "barrel/d.css": "",
                "barrel/types.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"barrel/a.css", "barrel/b.css", "barrel/c.css", "barrel/d.css"})

    def test_import_type_is_skipped(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import type { T } from './types';\nimport type Def from './def-type';\nimport './x.css';",
                "types.ts": "import './types.css';",
                "def-type.ts": "import './def-type.css';",
                "types.css": "",
                "def-type.css": "",
                "x.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"x.css"})
