import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class CMSAdminCSPSourceTests(SimpleTestCase):
    """Prevent source-owned CMS controls from bypassing enforcing CSP."""

    _INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=\s*[\"']", flags=re.IGNORECASE)

    def test_admin_templates_and_cms_javascript_have_no_inline_handlers(self):
        apps_root = settings.BASE_DIR / "apps"
        source_roots = [
            *apps_root.glob("*/templates/admin"),
            *apps_root.glob("*/static"),
        ]
        violations = []
        for root in source_roots:
            for path in sorted([*root.rglob("*.html"), *root.rglob("*.js")]):
                if "/vendor/" in path.as_posix():
                    continue
                source = path.read_text()
                for match in self._INLINE_HANDLER.finditer(source):
                    line = source[: match.start()].count("\n") + 1
                    violations.append(f"{path.relative_to(settings.BASE_DIR)}:{line}")

        self.assertEqual(violations, [])

    def test_source_owned_inline_admin_scripts_require_the_response_nonce(self):
        apps_root = settings.BASE_DIR / "apps"
        violations = []
        for root in apps_root.glob("*/templates/admin"):
            for path in root.rglob("*.html"):
                source = path.read_text()
                for match in re.finditer(r"<script\b(?P<attrs>[^>]*)>", source, flags=re.IGNORECASE):
                    attrs = match.group("attrs")
                    if re.search(r"\bsrc\s*=", attrs, flags=re.IGNORECASE):
                        continue
                    if 'nonce="{{ request.csp_nonce }}"' not in attrs:
                        line = source[: match.start()].count("\n") + 1
                        violations.append(f"{path.relative_to(settings.BASE_DIR)}:{line}")

        self.assertEqual(violations, [])

    def test_source_owned_inline_admin_styles_require_the_response_nonce(self):
        apps_root = settings.BASE_DIR / "apps"
        violations = []
        for root in apps_root.glob("*/templates/admin"):
            for path in root.rglob("*.html"):
                source = path.read_text()
                for match in re.finditer(r"<style\b(?P<attrs>[^>]*)>", source, flags=re.IGNORECASE):
                    if 'nonce="{{ request.csp_nonce }}"' not in match.group("attrs"):
                        line = source[: match.start()].count("\n") + 1
                        violations.append(f"{path.relative_to(settings.BASE_DIR)}:{line}")

        self.assertEqual(violations, [])

    def test_generated_srcdoc_styles_receive_the_response_nonce(self):
        preview_sources = (
            settings.BASE_DIR / "apps" / "cms" / "static" / "layout" / "js" / "menu" / "editor" / "render.js",
            settings.BASE_DIR / "apps" / "cms" / "static" / "layout" / "js" / "footer" / "editor" / "preview.js",
        )

        for path in preview_sources:
            with self.subTest(path=path.name):
                source = path.read_text()
                self.assertIn("window.I2G_CSP_NONCE", source)
                self.assertIn('<style nonce="${nonce}">', source)

    def test_material_web_receives_the_response_nonce(self):
        source = (settings.BASE_DIR / "apps" / "core" / "static" / "admin" / "js" / "csp-actions.js").read_text()

        self.assertIn("window.litNonce = window.I2G_CSP_NONCE", source)

    def test_material_web_remote_modules_are_version_pinned(self):
        source = (
            settings.BASE_DIR / "apps" / "core" / "static" / "admin" / "js" / "material-web-text-field.js"
        ).read_text()
        module_urls = re.findall(r'"(https://cdn\.jsdelivr\.net/npm/@material/web[^"]+)"', source)

        self.assertEqual(len(module_urls), 6)
        self.assertTrue(all("/@material/web@2.4.1/" in url for url in module_urls))
        self.assertTrue(all(url.endswith("/+esm") for url in module_urls))

    def test_admin_chart_dependencies_are_version_pinned(self):
        source = (
            settings.BASE_DIR / "apps" / "cms" / "templates" / "admin" / "cms" / "pageview" / "change_list.html"
        ).read_text()

        self.assertIn("chart.js@4.5.1/", source)
        self.assertIn("chartjs-plugin-datalabels@2.2.0/", source)
        self.assertNotRegex(source, r"chart(?:\.js|js-plugin-datalabels)@\d/")
        self.assertEqual(source.count('integrity="sha384-'), 2)
        self.assertEqual(source.count('crossorigin="anonymous"'), 2)

    def test_srcdoc_preview_is_sandboxed_without_script_permission(self):
        template = (
            settings.BASE_DIR / "apps" / "cms" / "templates" / "admin" / "cms" / "footer_content" / "change_form.html"
        ).read_text()

        self.assertIn('sandbox="allow-same-origin"', template)
        self.assertNotIn('sandbox="allow-same-origin allow-scripts"', template)

    def test_every_editor_action_is_allowlisted_by_the_csp_dispatcher(self):
        # csp-actions.js dispatches ``data-admin-call`` names through a hard-coded
        # allowlist and silently ignores unknown ones, so a control wired with
        # ``P.actionAttrs('newName', ...)`` but never allowlisted renders yet does
        # nothing. Keep the two in lock-step.
        dispatcher = (settings.BASE_DIR / "apps" / "core" / "static" / "admin" / "js" / "csp-actions.js").read_text()
        allowlist_block = re.search(r"ALLOWED_CALLS = new Set\(\[(.*?)\]\)", dispatcher, re.S)
        self.assertIsNotNone(allowlist_block)
        allowed = set(re.findall(r'"([A-Za-z0-9_]+)"', allowlist_block.group(1)))

        used = set()
        static_root = settings.BASE_DIR / "apps" / "cms" / "static"
        for path in static_root.rglob("*.js"):
            used.update(re.findall(r"actionAttrs\(\s*'([A-Za-z0-9_]+)'", path.read_text()))
        for path in (settings.BASE_DIR / "apps" / "cms" / "templates").rglob("*.html"):
            used.update(re.findall(r'data-admin-call="([A-Za-z0-9_]+)"', path.read_text()))

        self.assertTrue(used)
        self.assertEqual(sorted(used - allowed), [])

    def test_cms_editors_do_not_require_unsafe_eval(self):
        static_root = settings.BASE_DIR / "apps" / "cms" / "static"
        violations = []
        for path in static_root.rglob("*.js"):
            source = path.read_text()
            if re.search(r"\beval\s*\(|\bnew\s+Function\b", source):
                violations.append(str(path.relative_to(settings.BASE_DIR)))

        self.assertEqual(violations, [])

    def test_installed_unfold_alpine_bundle_is_csp_compatible(self):
        alpine_path = finders.find("unfold/js/alpine/alpine.js")

        self.assertIsNotNone(alpine_path)
        source = Path(alpine_path).read_text()
        self.assertNotRegex(source, r"\beval\s*\(|\b(?:new\s+)?(?:Async)?Function\s*\(")
