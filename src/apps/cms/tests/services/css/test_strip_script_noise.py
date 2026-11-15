import os

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.frontend_graph import (
    _STATIC_IMPORT_RE,
    SKIPPED_DIRS,
    entry_css_files,
    iter_css_files,
    read_text,
    strip_script_noise,
)
from apps.cms.tests.services.frontend_graph.test_frontend_graph import REAL_FRONTEND_DIR, make_tree


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
        # index.css -> styles/base/shared.css -> styles/base/tokens.css through CSS @import.
        self.assertIn("styles/base/tokens.css", entry)
        self.assertNotIn("features/projects/components/styles/cascade/projects.css", entry)
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
