import re

from django.conf import settings
from django.http import HttpResponse
from django.test import Client, override_settings

from apps.cms.models import CMSEmbedAllowedHost
from apps.cms.services.sanitization.embed_hosts import invalidate_cache
from apps.core.middleware import ContentSecurityPolicyMiddleware
from apps.core.tests.middleware.test_csp_middleware import _CSPHeaderCase


class CSPHeaderTests(_CSPHeaderCase):
    def test_nonce_is_unique_per_response(self):
        _, first_header = self._header()
        _, second_header = self._header()
        first_nonce = re.search(r"'nonce-([^']+)'", first_header)
        second_nonce = re.search(r"'nonce-([^']+)'", second_header)

        self.assertIsNotNone(first_nonce)
        self.assertIsNotNone(second_nonce)
        self.assertNotEqual(first_nonce.group(1), second_nonce.group(1))

    def test_does_not_rewrite_non_html_responses(self):
        def _json_view(_request):
            return HttpResponse('{"script":"<script>bad()</script>"}', content_type="application/json")

        response = ContentSecurityPolicyMiddleware(_json_view)(self.factory.get("/api/"))

        self.assertNotIn("nonce=", response.content.decode())

    def test_json_responses_get_a_short_static_policy(self):
        def _json_view(_request):
            return HttpResponse('{"ok": true}', content_type="application/json; charset=utf-8")

        middleware = ContentSecurityPolicyMiddleware(_json_view)
        first = middleware(self.factory.get("/projects/archive/"))["Content-Security-Policy-Report-Only"]
        second = middleware(self.factory.get("/projects/archive/"))["Content-Security-Policy-Report-Only"]

        self.assertEqual(first, "default-src 'none'; frame-ancestors 'none'")
        self.assertEqual(first, second)

    def test_drf_json_responses_get_the_static_policy(self):
        middleware = [*settings.MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"]
        with override_settings(MIDDLEWARE=middleware):
            json_response = Client().get("/projects/archive/", HTTP_ACCEPT="application/json")
            html_response = Client().get("/admin/login/")

        self.assertEqual(
            json_response["Content-Security-Policy-Report-Only"], "default-src 'none'; frame-ancestors 'none'"
        )
        self.assertIn("nonce-", html_response["Content-Security-Policy-Report-Only"])

    def test_problem_json_counts_as_json(self):
        def _problem_view(_request):
            return HttpResponse("{}", content_type="application/problem+json")

        response = ContentSecurityPolicyMiddleware(_problem_view)(self.factory.get("/"))

        self.assertNotIn("nonce-", response["Content-Security-Policy-Report-Only"])

    @override_settings(CSP_REPORT_ONLY=False)
    def test_json_policy_follows_the_enforcing_setting(self):
        def _json_view(_request):
            return HttpResponse("{}", content_type="application/json")

        response = ContentSecurityPolicyMiddleware(_json_view)(self.factory.get("/"))

        self.assertEqual(response["Content-Security-Policy"], "default-src 'none'; frame-ancestors 'none'")

    def test_preserves_explicit_frame_exemption(self):
        def _embeddable_view(_request):
            response = HttpResponse("embeddable")
            response.xframe_options_exempt = True
            return response

        response = ContentSecurityPolicyMiddleware(_embeddable_view)(self.factory.get("/cms/embed/example/"))

        self.assertNotIn("frame-ancestors", response["Content-Security-Policy-Report-Only"])

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

    def test_uses_active_cms_embed_hosts_and_ignores_inactive_hosts(self):
        CMSEmbedAllowedHost.objects.all().delete()
        CMSEmbedAllowedHost.objects.create(hostname="video.example.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="*.widgets.example.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="bad..example.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="inactive.example.com", is_active=False)
        invalidate_cache()
        self.addCleanup(invalidate_cache)

        _, header = self._header()

        self.assertIn("https://video.example.com", header)
        self.assertIn("https://*.widgets.example.com", header)
        self.assertNotIn("https://bad..example.com", header)
        self.assertNotIn("https://inactive.example.com", header)

    @override_settings(CSP_REPORT_ONLY=False)
    def test_can_promote_to_enforcing_header(self):
        response, _ = self._header()

        self.assertIn("Content-Security-Policy", response)
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    @override_settings(
        CSP_REPORT_ONLY=False,
        MIDDLEWARE=[*settings.MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"],
    )
    def test_enforcing_policy_renders_admin_login_with_nonces(self):
        response = Client().get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        header = response["Content-Security-Policy"]
        nonce_match = re.search(r"'nonce-([^']+)'", header)
        self.assertIsNotNone(nonce_match)
        nonce = nonce_match.group(1)
        html = response.content.decode()
        inline_scripts = [
            tag
            for tag in re.findall(r"<script\b[^>]*>", html, flags=re.IGNORECASE)
            if not re.search(r"\bsrc\s*=", tag, flags=re.IGNORECASE)
        ]
        style_elements = re.findall(r"<style\b[^>]*>", html, flags=re.IGNORECASE)
        self.assertTrue(style_elements)
        self.assertTrue(all(f'nonce="{nonce}"' in tag for tag in [*inline_scripts, *style_elements]))
        self.assertNotRegex(html, r"\son[a-z]+\s*=\s*[\"']")
        self.assertNotIn("'unsafe-eval'", header)
        self.assertIn("/static/admin/js/htmx-csp-config.js", html)
        self.assertLess(
            html.index("/static/unfold/js/htmx/htmx.js"),
            html.index("/static/admin/js/htmx-csp-config.js"),
        )
        self.assertLess(
            html.index("/static/admin/js/htmx-csp-config.js"),
            html.index("/static/unfold/js/app.js"),
        )

    @override_settings(
        CSP_REPORT_ONLY=False,
        MIDDLEWARE=[*settings.MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"],
    )
    def test_enforcing_policy_nonces_standalone_subscription_pages(self):
        client = Client()
        responses = [
            client.get("/mail/unsubscribe/invalid-token/"),
            client.post("/mail/resubscribe/invalid-token/"),
        ]

        for response in responses:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertEqual(response.status_code, 400)
                header = response["Content-Security-Policy"]
                nonce = re.search(r"'nonce-([^']+)'", header).group(1)
                style_elements = re.findall(
                    r"<style\b[^>]*>",
                    response.content.decode(),
                    flags=re.IGNORECASE,
                )
                self.assertTrue(style_elements)
                self.assertTrue(all(f'nonce="{nonce}"' in tag for tag in style_elements))
