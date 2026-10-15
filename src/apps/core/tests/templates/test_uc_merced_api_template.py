import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
from rest_framework.settings import api_settings


class UCMercedAPITemplateTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.template = get_template("rest_framework/uc_merced_api.html")

    def _render(self, **overrides):
        request = self.factory.get("/api/example/?format=api")
        request.user = AnonymousUser()
        context = {
            "name": "Example Endpoint",
            "description": "Public endpoint.",
            "request": request,
            "response": SimpleNamespace(status_code=200, status_text="OK"),
            "user": request.user,
            "paginator": None,
            "breadcrumblist": [("Api Root", "/api/"), ("Example Endpoint", "/api/example/")],
            "allowed_methods": ["GET", "HEAD", "OPTIONS"],
            "available_formats": ["json", "api"],
            "response_headers": {"Content-Type": "application/json"},
            "content": '{"value":"<script id=payload>alert(1)</script>"}',
            "put_form": None,
            "post_form": None,
            "delete_form": None,
            "options_form": True,
            "extra_actions": None,
            "filter_form": None,
            "raw_data_put_form": None,
            "raw_data_post_form": None,
            "raw_data_patch_form": None,
            "raw_data_put_or_patch_form": None,
            "display_edit_forms": True,
            "api_settings": api_settings,
            "csrf_header_name": "X-CSRFToken",
            "code_style": "",
        }
        context.update(overrides)
        return request, self.template.render(context, request=request)

    def test_read_only_page_renders_uc_merced_brand_without_creating_csrf_cookie(self):
        request, html = self._render()

        self.assertIn("<title>Example Endpoint | Innovate to Grow API | UC Merced</title>", html)
        self.assertIn('<header class="ucm-api__header">', html)
        self.assertIn('href="#ucm-api-main">Skip to main content</a>', html)
        self.assertIn('id="ucm-api-main"', html)
        self.assertIn('<footer class="ucm-api__footer">', html)
        self.assertIn('src="/static/images/ucmerced-logo.png"', html)
        self.assertIn('alt="University of California, Merced"', html)
        self.assertIn('href="/static/rest_framework/css/uc-merced-api.css"', html)
        self.assertIn('"csrfToken": ""', html)
        self.assertNotIn("Django REST framework", html)
        self.assertNotIn("i2glogo", html.lower())
        self.assertNotIn('<script id="payload">', html)
        self.assertNotIn("CSRF_COOKIE", request.META)
        self.assertNotIn("CSRF_COOKIE_NEEDS_UPDATE", request.META)

    def test_write_controls_receive_a_csrf_token(self):
        request, html = self._render(delete_form=True)

        self.assertRegex(html, r'"csrfToken": "[A-Za-z0-9]+"')
        self.assertTrue(request.META.get("CSRF_COOKIE"))
        self.assertTrue(request.META.get("CSRF_COOKIE_NEEDS_UPDATE"))

    def test_custom_template_adds_no_inline_executable_javascript(self):
        template_path = settings.BASE_DIR / "apps" / "core" / "templates" / "rest_framework" / "uc_merced_api.html"
        source = template_path.read_text()
        script_tags = re.findall(r"<script\b([^>]*)>", source, flags=re.DOTALL | re.IGNORECASE)

        self.assertGreater(len(script_tags), 1)
        for attributes in script_tags:
            self.assertTrue('src="' in attributes or 'type="application/json"' in attributes)
        self.assertNotIn("onclick=", source.lower())
        self.assertIn("nonce=\"{{ request.csp_nonce|default:'' }}\"", source)

    def test_static_brand_assets_are_resolvable_and_logo_is_an_exact_copy(self):
        css_result = finders.find("rest_framework/css/uc-merced-api.css")
        logo_result = finders.find("images/ucmerced-logo.png")

        self.assertIsNotNone(css_result)
        self.assertIsNotNone(logo_result)
        css = Path(css_result).read_text()
        logo = Path(logo_result).read_bytes()
        source_logo = (settings.BASE_DIR.parent / "pages" / "public" / "assets" / "images" / "ucmlogo.png").read_bytes()

        self.assertEqual(hashlib.sha256(logo).digest(), hashlib.sha256(source_logo).digest())
        self.assertIn("--ucm-blue: #002856", css)
        self.assertIn("--ucm-gold: #daa900", css)
        self.assertIn(".ucm-api .ucm-api__skip-link", css)
        self.assertIn(".ucm-api .ucm-api__header-inner::before", css)
        self.assertIn(".ucm-api .ucm-api__header-inner::after", css)
        self.assertIn("content: none", css)
        self.assertIn("@media (max-width: 767px)", css)
