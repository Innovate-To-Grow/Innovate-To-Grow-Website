import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase

from apps.core.middleware import csp_report
from apps.core.tests.request_limits.helpers import view_limit


class CSPReportEndpointTests(TestCase):
    """Cover the csp_report view that logs browser violation reports."""

    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def _post(self, body, content_type="application/json"):
        request = self.factory.post("/csp-report/", data=body, content_type=content_type)
        return csp_report(request)

    def test_valid_report_is_logged_with_sanitized_fields(self):
        body = json.dumps(
            {
                "csp-report": {
                    "violated-directive": "script-src",
                    "blocked-uri": "https://user:secret@evil.example/x\n.js?token=secret#fragment",
                    "document-uri": "https://site.example/mail/unsubscribe/sensitive-token/?next=secret",
                    "source-file": "https://site.example/app.js",
                }
            }
        )
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        warn.assert_called_once()
        # The newline in blocked-uri must be sanitized out of the logged args.
        logged_args = warn.call_args.args
        self.assertIn("script-src", logged_args)
        self.assertTrue(all("\n" not in str(a) for a in logged_args))
        self.assertTrue(all("secret" not in str(a) for a in logged_args))
        self.assertTrue(all("token=" not in str(a) for a in logged_args))
        self.assertTrue(all("sensitive-token" not in str(a) for a in logged_args))
        self.assertIn("https://site.example/mail/unsubscribe/<redacted>/", logged_args)

    def test_url_with_invalid_port_does_not_fall_back_to_logging_secrets(self):
        body = json.dumps(
            {
                "csp-report": {
                    "effective-directive": "connect-src",
                    "blocked-uri": "https://user:secret@evil.example:bad/path?token=secret",
                }
            }
        )

        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            response = self._post(body)

        self.assertEqual(response.status_code, 204)
        logged_args = warn.call_args.args
        self.assertTrue(all("secret" not in str(value) for value in logged_args))
        self.assertTrue(all("token=" not in str(value) for value in logged_args))

    def test_falls_back_to_effective_directive(self):
        body = json.dumps({"csp-report": {"effective-directive": "img-src"}})
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        self.assertIn("img-src", warn.call_args.args)

    def test_unparseable_body_returns_204_and_warns(self):
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            response = self._post(b"\xff\xfe not json", content_type="application/json")
        self.assertEqual(response.status_code, 204)
        self.assertIn("unparseable body", warn.call_args.args[0])

    def test_missing_csp_report_object_returns_204(self):
        body = json.dumps({"something-else": True})
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        self.assertIn("missing 'csp-report' object", warn.call_args.args[0])

    def test_non_dict_payload_returns_204(self):
        body = json.dumps(["not", "a", "dict"])
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            response = self._post(body)
        self.assertEqual(response.status_code, 204)
        self.assertIn("missing 'csp-report' object", warn.call_args.args[0])

    def test_unexpected_error_is_caught(self):
        # Force an exception after parsing by making .get raise via a bad object.
        request = self.factory.post("/csp-report/", data="{}", content_type="application/json")
        with (
            patch("apps.core.middleware.csp_report.json.loads", side_effect=RuntimeError("boom")),
            patch("apps.core.middleware.csp_report.logger.exception") as exc_log,
        ):
            response = csp_report(request)
        self.assertEqual(response.status_code, 204)
        exc_log.assert_called_once()

    def test_get_method_not_allowed(self):
        # require_POST decorator rejects GET via the URL dispatcher.
        client = Client()
        response = client.get("/csp-report/")
        self.assertEqual(response.status_code, 405)

    @view_limit(**{"view-csp-report": (1, 60)})
    def test_reports_are_rate_limited_without_logging_attacker_content(self):
        body = json.dumps({"csp-report": {"effective-directive": "img-src"}})
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            first = self._post(body)
            second = self._post(body)

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 204)
        warn.assert_called_once()

    def test_oversized_report_is_rejected(self):
        response = self._post(json.dumps({"csp-report": {"blocked-uri": "x" * 5000}}))

        self.assertEqual(response.status_code, 413)
