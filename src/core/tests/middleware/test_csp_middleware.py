"""Tests for ContentSecurityPolicyMiddleware.

These tests lock in the `frame-src` allowlist so a regression that silently
drops an embed provider (YouTube, Google Docs, Calendly, etc.) fails CI
instead of only being caught by a report-uri violation in production.
"""

from django.test import RequestFactory, TestCase

from core.middleware import ContentSecurityPolicyMiddleware


class CSPHeaderTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        def _view(_request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        self.middleware = ContentSecurityPolicyMiddleware(_view)

    def _header(self):
        request = self.factory.get("/")
        response = self.middleware(request)
        return response, response.get("Content-Security-Policy-Report-Only", "")

    def test_adds_report_only_header(self):
        response, header = self._header()
        self.assertIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn("Content-Security-Policy", response)
        self.assertTrue(header, "Report-only header must be non-empty")

    def test_frame_src_allows_seeded_hosts(self):
        _, header = self._header()
        expected_frame_src_entries = [
            "https://www.youtube.com",
            "https://*.youtube.com",
            "https://www.youtube-nocookie.com",
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

    def test_does_not_overwrite_existing_enforcing_header(self):
        def _view_with_enforcing(_request):
            from django.http import HttpResponse

            response = HttpResponse("ok")
            response["Content-Security-Policy"] = "default-src 'none'"
            return response

        mw = ContentSecurityPolicyMiddleware(_view_with_enforcing)
        response = mw(self.factory.get("/"))
        self.assertEqual(response["Content-Security-Policy"], "default-src 'none'")
        self.assertNotIn("Content-Security-Policy-Report-Only", response)
