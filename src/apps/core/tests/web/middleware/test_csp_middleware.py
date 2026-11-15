"""Tests for ContentSecurityPolicyMiddleware.

These tests lock in the `frame-src` allowlist so a regression that silently
drops an embed provider (YouTube, Google Docs, Calendly, etc.) fails CI
instead of only being caught by a report-uri violation in production.
"""

import re

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.core.middleware import ContentSecurityPolicyMiddleware


class _CSPHeaderCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

        def _view(_request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        self.middleware = ContentSecurityPolicyMiddleware(_view)

    def _header(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        return response, response.get("Content-Security-Policy-Report-Only", "")


class CSPHeaderTests(_CSPHeaderCase):
    def test_adds_report_only_header(self):
        response, header = self._header()
        self.assertIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn("Content-Security-Policy", response)
        self.assertTrue(header, "Report-only header must be non-empty")

    def test_frame_src_allows_seeded_hosts(self):
        _, header = self._header()
        expected_frame_src_entries = [
            "'self'",
            "https://youtube.com",
            "https://*.youtube.com",
            "https://youtube-nocookie.com",
            "https://*.youtube-nocookie.com",
            "https://player.vimeo.com",
            "https://*.vimeo.com",
            "https://docs.google.com",
            "https://forms.google.com",
            "https://www.google.com",
            "https://calendly.com",
            "https://*.calendly.com",
            "https://www.figma.com",
            "https://codesandbox.io",
            "https://*.codesandbox.io",
            "https://www.typeform.com",
            "https://form.typeform.com",
        ]
        for entry in expected_frame_src_entries:
            self.assertIn(entry, header, f"{entry!r} must be allowed by frame-src")

    def test_reports_violations_to_local_endpoint(self):
        _, header = self._header()
        self.assertIn("report-uri /csp-report/", header)

    def test_script_src_allows_admin_material_web_dependencies(self):
        _, header = self._header()
        self.assertIn("script-src 'self'", header)
        self.assertIn("https://cdn.jsdelivr.net", header)
        self.assertNotIn("https://esm.run", header)

    @override_settings(
        STATIC_URL="https://static.example.test/static/",
        MEDIA_URL="https://media.example.test/media/",
        FRONTEND_URL="https://frontend.example.test/app/",
        CSP_STYLE_SOURCES=("'self'", "https://fonts.googleapis.com"),
        CSP_FONT_SOURCES=("'self'", "data:", "https://fonts.gstatic.com"),
        CSP_CONNECT_SOURCES=(
            "'self'",
            "https://fonts.googleapis.com",
            "https://fonts.gstatic.com",
        ),
    )
    def test_allows_exact_storage_and_font_origins(self):
        _, header = self._header()

        self.assertIn("https://static.example.test", header)
        self.assertIn("https://media.example.test", header)
        self.assertIn("style-src 'self' https://fonts.googleapis.com", header)
        self.assertIn("font-src 'self' data: https://fonts.gstatic.com", header)
        self.assertIn("frame-src 'self' https://frontend.example.test", header)
        self.assertIn(
            "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://frontend.example.test",
            header,
        )
        self.assertNotIn("img-src 'self' data: https:", header)

    @override_settings(
        STATIC_URL="https://user:secret@static.example.test:8443/static/",
        MEDIA_URL="/media/",
    )
    def test_asset_origins_never_expose_url_credentials(self):
        _, header = self._header()

        self.assertIn("https://static.example.test:8443", header)
        self.assertNotIn("user", header)
        self.assertNotIn("secret", header)

    def test_disables_inline_script_handlers_without_broad_script_exception(self):
        _, header = self._header()
        directives = {part.strip().split(" ", 1)[0]: part.strip() for part in header.split(";") if part.strip()}

        self.assertEqual(directives["script-src-attr"], "script-src-attr 'none'")
        self.assertNotIn("'unsafe-inline'", directives["script-src"])
        self.assertNotIn("'unsafe-eval'", directives["script-src"])
        self.assertNotIn("'unsafe-inline'", directives["style-src"])
        # This intentionally narrow compatibility rule supports style=""
        # attributes emitted by Django Admin/Unfold and vendored widgets.
        self.assertEqual(directives["style-src-attr"], "style-src-attr 'unsafe-inline'")

    def test_nonces_only_trusted_vendor_styles_without_blessing_injected_markup(self):
        def _html_view(_request):
            return HttpResponse(
                '<html><head><style id="unfold-theme-colors">:root{--ok:green}</style>'
                "<style>.injected{color:red}</style></head>"
                "<body><script>window.injected=true</script></body></html>"
            )

        response = ContentSecurityPolicyMiddleware(_html_view)(self.factory.get("/admin/"))
        header = response["Content-Security-Policy-Report-Only"]
        match = re.search(r"'nonce-([^']+)'", header)
        self.assertIsNotNone(match)
        nonce = match.group(1)
        html = response.content.decode()

        self.assertEqual(html.count(f'nonce="{nonce}"'), 1)
        self.assertIn(f'<style id="unfold-theme-colors" nonce="{nonce}">', html)
        self.assertIn("<style>.injected{color:red}</style>", html)
        self.assertIn("<script>window.injected=true</script>", html)

    def test_preserves_explicit_style_nonce(self):
        def _html_view(_request):
            return HttpResponse('<style id="unfold-theme-colors" nonce="template-nonce">.ok{display:block}</style>')

        response = ContentSecurityPolicyMiddleware(_html_view)(self.factory.get("/"))

        self.assertIn('nonce="template-nonce"', response.content.decode())
        self.assertEqual(response.content.decode().count("nonce="), 1)

    def test_vendor_style_rewrite_updates_content_length(self):
        def _html_view(_request):
            response = HttpResponse('<style id="unfold-theme-colors">.ok{display:block}</style>')
            response["Content-Length"] = str(len(response.content))
            return response

        response = ContentSecurityPolicyMiddleware(_html_view)(self.factory.get("/"))

        self.assertIn("nonce=", response.content.decode())
        self.assertEqual(int(response["Content-Length"]), len(response.content))

    def test_nonces_unfold_changelist_compatibility_style(self):
        def _html_view(_request):
            return HttpResponse("<style>\n  #changelist table thead th:first-child {width: inherit}\n</style>")

        response = ContentSecurityPolicyMiddleware(_html_view)(self.factory.get("/admin/example/"))
        nonce = re.search(
            r"'nonce-([^']+)'",
            response["Content-Security-Policy-Report-Only"],
        ).group(1)

        self.assertIn(f'<style nonce="{nonce}">', response.content.decode())
