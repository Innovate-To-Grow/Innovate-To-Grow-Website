"""Tests for ContentSecurityPolicyMiddleware.

These tests lock in the `frame-src` allowlist so a regression that silently
drops an embed provider (YouTube, Google Docs, Calendly, etc.) fails CI
instead of only being caught by a report-uri violation in production.
"""

import json
from pathlib import Path
from unittest.mock import patch

from django.test import Client, RequestFactory, TestCase

from apps.core.middleware import ContentSecurityPolicyMiddleware, csp_report


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
            "'self'",
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

    def test_script_src_allows_only_required_admin_script_hosts(self):
        _, header = self._header()
        self.assertIn("script-src 'self'", header)
        self.assertIn("https://esm.run", header)
        self.assertIn("https://cdnjs.cloudflare.com", header)
        self.assertNotIn("https://cdn.jsdelivr.net", header)

    def test_pageview_admin_uses_local_chart_asset(self):
        template = (
            Path(__file__).resolve().parents[3]
            / "cms"
            / "templates"
            / "admin"
            / "cms"
            / "pageview"
            / "change_list.html"
        ).read_text()
        self.assertIn("{% static 'cms/js/pageview_charts.js' %}", template)
        self.assertNotIn("cdn.jsdelivr.net", template)
        self.assertNotIn("chart.js@", template)

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


class CSPReportEndpointTests(TestCase):
    """Cover the csp_report view that logs browser violation reports."""

    def setUp(self):
        self.factory = RequestFactory()

    def _post(self, body, content_type="application/json"):
        request = self.factory.post("/csp-report/", data=body, content_type=content_type)
        return csp_report(request)

    def test_valid_report_is_logged_with_sanitized_fields(self):
        body = json.dumps(
            {
                "csp-report": {
                    "violated-directive": "script-src",
                    "blocked-uri": "https://evil.example/x\n.js",
                    "document-uri": "https://site.example/page",
                    "source-file": "https://site.example/app.js",
                }
            }
        )
        with patch("apps.core.middleware.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        warn.assert_called_once()
        # The newline in blocked-uri must be sanitized out of the logged args.
        logged_args = warn.call_args.args
        self.assertIn("script-src", logged_args)
        self.assertTrue(all("\n" not in str(a) for a in logged_args))

    def test_falls_back_to_effective_directive(self):
        body = json.dumps({"csp-report": {"effective-directive": "img-src"}})
        with patch("apps.core.middleware.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        self.assertIn("img-src", warn.call_args.args)

    def test_unparseable_body_returns_204_and_warns(self):
        with patch("apps.core.middleware.logger.warning") as warn:
            response = self._post(b"\xff\xfe not json", content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.assertIn("unparseable body", warn.call_args.args[0])

    def test_missing_csp_report_object_returns_204(self):
        body = json.dumps({"something-else": True})
        with patch("apps.core.middleware.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        self.assertIn("missing 'csp-report' object", warn.call_args.args[0])

    def test_non_dict_payload_returns_204(self):
        body = json.dumps(["not", "a", "dict"])
        with patch("apps.core.middleware.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        self.assertIn("missing 'csp-report' object", warn.call_args.args[0])

    def test_unexpected_error_is_caught(self):
        # Force an exception after parsing by making .get raise via a bad object.
        request = self.factory.post("/csp-report/", data="{}", content_type="application/json")
        with (
            patch("apps.core.middleware.json.loads", side_effect=RuntimeError("boom")),
            patch("apps.core.middleware.logger.exception") as exc_log,
        ):
            response = csp_report(request)
        self.assertEqual(response.status_code, 204)
        exc_log.assert_called_once()

    def test_get_method_not_allowed(self):
        # require_POST decorator rejects GET via the URL dispatcher.
        client = Client()
        response = client.get("/csp-report/")
        self.assertEqual(response.status_code, 405)
