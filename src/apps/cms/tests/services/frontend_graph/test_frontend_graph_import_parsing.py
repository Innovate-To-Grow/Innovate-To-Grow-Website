from apps.cms.services.styles.frontend_graph import (
    entry_css_files,
)
from apps.cms.tests.services.frontend_graph.test_frontend_graph import _EntryCssFilesCase, make_tree


class EntryCssFilesTests(_EntryCssFilesCase):
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
