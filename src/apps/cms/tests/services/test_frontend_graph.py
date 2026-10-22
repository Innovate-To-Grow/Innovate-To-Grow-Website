"""Tests for ``apps.cms.services.styles.frontend_graph`` (which frontend CSS files the entry bundle loads)."""

import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.frontend_graph import (
    _STATIC_IMPORT_RE,
    ENTRY_MODULE,
    SKIPPED_DIRS,
    entry_css_files,
    iter_css_files,
    read_text,
    strip_script_noise,
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


class EntryCssFilesTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

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

    def test_alias_and_relative_resolution(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "import '@/features/feature';\n"
                    "import './app/Shell';\n"
                    "import '@/lib';\n"
                    "import './explicit.ts';\n"
                    "import './plain.js';\n"
                    "import './comp.jsx';\n"
                    "import './esm.mjs';\n"
                    "import '@/styles/alias.css';\n"
                ),
                # Extensionless: .ts, .tsx, .js, .jsx and .mjs are tried in turn.
                "features/feature.ts": "import '../shared/parent';",
                "shared/parent.tsx": "import './parent.css';",
                "app/Shell/index.tsx": "import '../../shell.css';\nimport './sub';",
                "app/Shell/sub/index.ts": "import './sub.css';",
                "lib/index.js": "import './lib.css';",
                "explicit.ts": "import './explicit.css';",
                "plain.js": "import './plain.css';",
                "comp.jsx": "import './comp.css';",
                "esm.mjs": "import './esm.css';",
                "styles/alias.css": "",
                "shared/parent.css": "",
                "shell.css": "",
                "app/Shell/sub/sub.css": "",
                "lib/lib.css": "",
                "explicit.css": "",
                "plain.css": "",
                "comp.css": "",
                "esm.css": "",
            },
        )

        self.assertEqual(
            entry_css_files(root),
            {
                "styles/alias.css",
                "shared/parent.css",
                "shell.css",
                "app/Shell/sub/sub.css",
                "lib/lib.css",
                "explicit.css",
                "plain.css",
                "comp.css",
                "esm.css",
            },
        )

    def test_js_specifiers_fall_back_to_their_typescript_source(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "import './util.js';\n"
                    "import './view.js';\n"
                    "import './comp.jsx';\n"
                    "import './esm.mjs';\n"
                    "import '@/lib/alias.js';\n"
                ),
                # .js -> .ts then .tsx; .jsx -> .tsx; .mjs -> .mts (what Vite does for a TS importer).
                "util.ts": "import './util.css';",
                "view.tsx": "import './view.css';",
                "comp.tsx": "import './comp.css';",
                "esm.mts": "import './esm.css';",
                "lib/alias.ts": "import './alias.css';",
                "util.css": "",
                "view.css": "",
                "comp.css": "",
                "esm.css": "",
                "lib/alias.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"util.css", "view.css", "comp.css", "esm.css", "lib/alias.css"})

    def test_a_real_js_file_wins_over_its_typescript_source(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './both.js';",
                "both.js": "import './from-js.css';",
                "both.ts": "import './from-ts.css';",
                "from-js.css": "",
                "from-ts.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"from-js.css"})

    def test_a_jsx_specifier_does_not_fall_back_to_a_ts_file(self):
        root = make_tree(self, {"main.tsx": "import './comp.jsx';", "comp.ts": "import './c.css';", "c.css": ""})
        self.assertEqual(entry_css_files(root), set())

    def test_a_module_file_wins_over_an_index_file(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './thing';",
                "thing.ts": "import './file.css';",
                "thing/index.ts": "import './index.css';",
                "file.css": "",
                "thing/index.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"file.css"})

    def test_dynamic_imports_and_react_lazy_are_skipped(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "import { lazy } from 'react';\n"
                    "import './entry.css';\n"
                    "const Route = React.lazy(() => import('./routes/Route'));\n"
                    "const Other = lazy(() =>\n  import('./routes/Other'),\n);\n"
                    "import('./routes/Bare');\n"
                    'const mod = await import("./routes/Awaited");\n'
                ),
                "routes/Route.tsx": "import './Route.css';",
                "routes/Other.tsx": "import './Other.css';",
                "routes/Bare.tsx": "import './Bare.css';",
                "routes/Awaited.ts": "import './Awaited.css';",
                "entry.css": "",
                "routes/Route.css": "",
                "routes/Other.css": "",
                "routes/Bare.css": "",
                "routes/Awaited.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"entry.css"})

    def test_comments_and_template_literals_hide_imports(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "// import './ghost-line.css';\n"
                    "/* import './ghost-block.css'; */\n"
                    "/*\n * import './ghost-doc.css';\n */\n"
                    "const md = `\nimport './ghost-template.css';\nexport * from './ghost-reexport';\n`;\n"
                    "const one = `import x from './ghost-inline.css'`;\n"
                    "/* lead */ import './after-comment.css';\n"
                    "import './real.css'; // import './ghost-trailing.css';\n"
                    "import './last.css'; /* never closed import './ghost-open.css';"
                ),
                "ghost-reexport.ts": "import './ghost-reexport.css';",
                "ghost-line.css": "",
                "ghost-block.css": "",
                "ghost-doc.css": "",
                "ghost-template.css": "",
                "ghost-reexport.css": "",
                "ghost-inline.css": "",
                "ghost-trailing.css": "",
                "ghost-open.css": "",
                "after-comment.css": "",
                "real.css": "",
                "last.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"after-comment.css", "real.css", "last.css"})

    def test_a_string_holding_comment_markers_does_not_hide_the_next_import(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "const url = 'https://cdn.example.test/lib.js'; import './after-url.css';\n"
                    "const star = \"/*\"; import './after-star.css'; // */\n"
                    "const tick = '`'; import './after-tick.css';\n"
                ),
                "after-url.css": "",
                "after-star.css": "",
                "after-tick.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"after-url.css", "after-star.css", "after-tick.css"})

    def test_an_import_clause_holds_only_clause_characters(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    # JSX text: "from" and a quoted path after code that no import clause can hold.
                    "export const Credit = () => <p>Copied from './ghost-jsx.css'</p>;\n"
                    # A quote or semicolon ends the clause, so it cannot reach into the next statement.
                    "export { helper }; let from\n'./ghost-semicolon.css'\n"
                    'export default "x"\nfrom\n"./ghost-quote.css"\n'
                    "import './real.css';\n"
                ),
                "ghost-jsx.css": "",
                "ghost-semicolon.css": "",
                "ghost-quote.css": "",
                "real.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"real.css"})

    def test_an_import_after_a_closing_brace_on_the_same_line_is_followed(self):
        root = make_tree(self, {"main.tsx": "if (x) { y(); } import './after-brace.css';", "after-brace.css": ""})
        self.assertEqual(entry_css_files(root), {"after-brace.css"})

    def test_export_star_as_namespace_is_followed(self):
        root = make_tree(
            self,
            {
                "main.tsx": "export * as ns from './ns';\nexport * as\n  other from \"./other\";\nexport * as $x from'./x';",
                "ns.ts": "import './ns.css';",
                "other.ts": "import './other.css';",
                "x.ts": "import './x.css';",
                "ns.css": "",
                "other.css": "",
                "x.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"ns.css", "other.css", "x.css"})

    def test_css_import_is_followed(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './index.css';",
                "index.css": (
                    "@import './assets/shared.css';\n"
                    '@import url("./quoted-url.css");\n'
                    "@import url( '@/aliased.css' ) layer(base);\n"
                    ".a {}"
                ),
                "assets/shared.css": '@import "../deep/tokens.css";',
                "deep/tokens.css": ":root {}",
                "quoted-url.css": "",
                "aliased.css": "",
                "not-imported.css": "",
            },
        )
        self.assertEqual(
            entry_css_files(root),
            {"index.css", "assets/shared.css", "deep/tokens.css", "quoted-url.css", "aliased.css"},
        )

    def test_bare_css_import_resolves_relative_to_the_importing_file(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './index.css';",
                "index.css": "@import 'sibling.css';\n@import \"assets/nested.css\";",
                "sibling.css": "",
                "assets/nested.css": "@import 'deeper.css';",
                "assets/deeper.css": "",
                "deeper.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"index.css", "sibling.css", "assets/nested.css", "assets/deeper.css"})

    def test_a_bare_script_import_is_still_a_package(self):
        # Relative-first resolution applies to CSS @import only.
        root = make_tree(
            self, {"main.tsx": "import 'sibling.css';\nimport 'helper';", "sibling.css": "", "helper.ts": ""}
        )
        self.assertEqual(entry_css_files(root), set())

    def test_unquoted_css_import_url_is_followed(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './index.css';",
                "index.css": "@import url(./x.css);\n@import url( ../src/y.css ) screen;\n@import url(bare.css);",
                "x.css": "",
                "y.css": "",
                "bare.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"index.css", "x.css", "y.css", "bare.css"})

    def test_css_comments_and_remote_imports_are_not_followed(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './index.css';",
                "index.css": (
                    "/* @import './ghost.css'; */\n"
                    "/*\n@import url(./ghost-url.css);\n*/\n"
                    "@import url(https://fonts.example.test/css2?family=X);\n"
                    "@import 'https://cdn.example.test/remote.css';\n"
                    "@import './real.css';"
                ),
                "ghost.css": "",
                "ghost-url.css": "",
                "real.css": "",
            },
        )
        self.assertEqual(entry_css_files(root), {"index.css", "real.css"})

    def test_bare_packages_and_unresolvable_specifiers_are_ignored(self):
        root = make_tree(
            self,
            {
                "main.tsx": (
                    "import React from 'react';\n"
                    "import 'some-pkg/style.css';\n"
                    "import fs from 'node:fs';\n"
                    "import './missing';\n"
                    "import logo from './logo.svg';\n"
                    "import data from './data.json';\n"
                    "import './index.css';\n"
                ),
                # normalize.css is not next to index.css, so the relative-first lookup finds nothing.
                "index.css": "@import 'normalize.css';\n@import './gone.css';",
                "node_modules/some-pkg/style.css": ".pkg {}",
                "node_modules/normalize.css/normalize.css": "",
                "logo.svg": "<svg/>",
                "data.json": "{}",
            },
        )
        self.assertEqual(entry_css_files(root), {"index.css"})

    def test_import_cycles_terminate(self):
        root = make_tree(
            self,
            {
                "main.tsx": "import './a';",
                "a.ts": "import './b';\nimport './a.css';",
                "b.ts": "import './a';\nimport './main';\nimport './b.css';",
                "a.css": "@import './b.css';",
                "b.css": "@import './a.css';",
            },
        )
        self.assertEqual(entry_css_files(root), {"a.css", "b.css"})

    def test_files_outside_the_frontend_dir_are_left_out(self):
        root = make_tree(self, {"main.tsx": "import '../outside.css';\nimport './inside.css';", "inside.css": ""})
        (root.parent / "outside.css").write_text(".out {}", encoding="utf-8")

        self.assertEqual(entry_css_files(root), {"inside.css"})


class StripScriptNoiseTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_comments_are_blanked(self):
        self.assertEqual(strip_script_noise("a // note\nb"), "a \nb")
        self.assertEqual(strip_script_noise("a /* note */ b"), "a   b")
        self.assertEqual(strip_script_noise("a /* one\ntwo */b"), "a  b")

    def test_comments_running_to_the_end_of_the_text(self):
        self.assertEqual(strip_script_noise("x // end"), "x ")
        self.assertEqual(strip_script_noise("x /* never closed"), "x  ")

    def test_template_literals_are_emptied(self):
        self.assertEqual(strip_script_noise("x = `a ${b} 'c'\nimport './d.css'`;"), "x = ``;")
        self.assertEqual(strip_script_noise("`a\\`b` + 1"), "`` + 1")
        self.assertEqual(strip_script_noise("`never closed"), "``")

    def test_quoted_strings_are_kept_with_their_comment_markers(self):
        for text in (
            "s = 'https://example.test/x'",
            's = "/* not a comment */"',
            "s = 'it\\'s // still the string'",
            "s = '`'",
        ):
            with self.subTest(text=text):
                self.assertEqual(strip_script_noise(text), text)

    def test_an_unclosed_quote_stops_at_the_end_of_its_line(self):
        self.assertEqual(strip_script_noise("<p>Don't</p>\n// gone\nnext"), "<p>Don't</p>\n\nnext")
        self.assertEqual(strip_script_noise('s = "open'), 's = "open')

    def test_regex_literals_are_blanked_so_they_cannot_hide_later_imports(self):
        for code in (
            'const r = /`/g;\nexport * from "./b";',
            'const r = /\\/*/;\nexport * from "./b";',
            'if (/["\']/.test(s)) {}\nexport * from "./b";',
            'function f() { return /[/]`/.test(x); }\nexport * from "./b";',
        ):
            with self.subTest(code=code):
                self.assertEqual(_STATIC_IMPORT_RE.findall(strip_script_noise(code)), [("", "./b")])

    def test_division_and_jsx_closing_tags_are_not_regex_literals(self):
        self.assertEqual(strip_script_noise("x = a / b / c;"), "x = a / b / c;")
        self.assertEqual(strip_script_noise("<div>a</div>"), "<div>a</div>")


class StaticImportPatternTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_a_default_import_named_type_is_followed(self):
        self.assertEqual(_STATIC_IMPORT_RE.findall('import type from "./typedefault";'), [("", "./typedefault")])

    def test_type_only_imports_are_marked(self):
        self.assertEqual(_STATIC_IMPORT_RE.findall('import type {X} from "./t";'), [("type ", "./t")])


class RealFrontendEntryTests(SimpleTestCase):
    """The real ``pages/src`` graph: shell CSS is in the entry bundle, the projects route CSS is not."""

    def setUp(self):
        cache.clear()

    def test_real_entry_bundle(self):
        entry = entry_css_files(REAL_FRONTEND_DIR)

        self.assertIsNotNone(entry)
        self.assertIn("app/MaintenanceMode/MaintenanceMode.css", entry)
        self.assertIn("index.css", entry)
        # index.css -> assets/shared.css -> assets/tokens.css through CSS @import.
        self.assertIn("assets/tokens.css", entry)
        self.assertNotIn("features/projects/components/projects.css", entry)
        for relative in entry:
            with self.subTest(file=relative):
                self.assertTrue((REAL_FRONTEND_DIR / relative).is_file())


class IterCssFilesTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _relative(self, root):
        return [path.relative_to(root).as_posix() for path in iter_css_files(root)]

    def test_lists_css_files_sorted_and_skips_dependency_build_and_test_dirs(self):
        self.assertEqual(SKIPPED_DIRS, frozenset({"node_modules", "dist", "__tests__"}))
        root = make_tree(
            self,
            {
                "z.css": "",
                "a/b/c.css": "",
                "dist.css": "",
                "distribution/kept.css": "",
                "node_modules/pkg/x.css": "",
                "features/node_modules/y.css": "",
                "dist/assets/index.css": "",
                "__tests__/fixture.css": "",
                "features/__tests__/f.css": "",
                "features/a.ts": "",
                "features/a.scss": "",
            },
        )

        self.assertEqual(self._relative(root), ["a/b/c.css", "dist.css", "distribution/kept.css", "z.css"])

    def test_skips_directories_named_like_css_files_and_dangling_symlinks(self):
        root = make_tree(self, {"real.css": "", "folder.css/inner.css": ""})
        (root / "gone.css").symlink_to(root / "no-such-target.css")
        (root / "alias.css").symlink_to(root / "real.css")

        self.assertEqual(self._relative(root), ["alias.css", "folder.css/inner.css", "real.css"])

    def test_missing_root_yields_nothing(self):
        root = make_tree(self, {})
        self.assertEqual(list(iter_css_files(root / "missing")), [])


class ReadTextTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_reads_utf8(self):
        root = make_tree(self, {"a.css": '.café::before { content: "✓"; }'})
        self.assertEqual(read_text(root / "a.css"), '.café::before { content: "✓"; }')

    def test_latin1_bytes_are_replaced_not_fatal(self):
        root = make_tree(self, {"latin.css": b".caf\xe9 { color: red; }\n.ok {}"})

        text = read_text(root / "latin.css")

        self.assertEqual(text, ".caf� { color: red; }\n.ok {}")

    def test_unreadable_paths_read_as_empty(self):
        root = make_tree(self, {"dir.css/x.css": ""})
        self.assertEqual(read_text(root / "missing.css"), "")
        self.assertEqual(read_text(root / "dir.css"), "")

    def test_unreadable_file_reads_as_empty(self):
        if os.geteuid() == 0:
            self.skipTest("root can read a file without read permission")
        root = make_tree(self, {"locked.css": ".a {}"})
        path = root / "locked.css"
        path.chmod(0)
        self.addCleanup(path.chmod, 0o644)

        self.assertEqual(read_text(path), "")
