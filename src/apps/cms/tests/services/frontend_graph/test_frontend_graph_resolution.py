from apps.cms.services.styles.frontend_graph import (
    entry_css_files,
)
from apps.cms.tests.services.frontend_graph.test_frontend_graph import _EntryCssFilesCase, make_tree


class EntryCssFilesTests(_EntryCssFilesCase):
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
