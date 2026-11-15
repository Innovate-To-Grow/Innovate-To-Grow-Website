import json
import re

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.admin.cms.page_admin.editor import save_blocks_from_json
from apps.cms.models import CMSPage
from apps.cms.tests.admin.editor.test_cms_admin import Member, _MessageCollector


class _CMSPageChangeFormRenderCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Editor",
            last_name="Admin",
        )
        ContactEmail.objects.create(
            member=self.admin_user, email_address="editor@example.com", email_type="primary", verified=True
        )
        self.client.login(username="editor@example.com", password="testpass123")
        self.page = CMSPage.objects.create(
            slug="test-editor-page",
            route="/test-editor-page",
            title="Test Editor Page",
            status="draft",
        )

    def tearDown(self):
        cache.clear()

    def _save_embed_widget_blocks(self, blocks):
        request = type("Request", (), {"POST": {"blocks_json": json.dumps(blocks)}})()
        messages = _MessageCollector()
        save_blocks_from_json(request, self.page, messages)
        return messages


class CMSPageChangeFormRenderTests(_CMSPageChangeFormRenderCase):
    """Tests that the CMS page change form renders correctly with editor JS config."""

    def test_change_form_renders_for_staff_user(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # The live-preview sync backs off on 429 with the shared admin helper, loaded before it.
        html = response.content.decode()
        self.assertLess(html.index("admin/js/poll-backoff.js"), html.index("block-editor/live-preview.js"))

    @override_settings(
        CSP_REPORT_ONLY=False,
        MIDDLEWARE=[*settings.MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"],
    )
    def test_change_form_renders_under_enforcing_csp_without_inline_handlers(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)

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
        self.assertTrue(inline_scripts)
        self.assertTrue(style_elements)
        self.assertTrue(all(f'nonce="{nonce}"' in tag for tag in [*inline_scripts, *style_elements]))
        self.assertNotRegex(html, r"\son[a-z]+\s*=\s*[\"']")
        self.assertIn(
            f'nonce="{nonce}" src="/static/admin/js/csp-actions.js',
            html,
        )
        self.assertLess(
            html.index("/static/admin/js/csp-actions.js"),
            html.index("/static/admin/js/material-web-text-field.js"),
        )

    @override_settings(
        CSP_REPORT_ONLY=False,
        MIDDLEWARE=[*settings.MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"],
    )
    def test_pageview_dashboard_renders_under_enforcing_csp(self):
        response = self.client.get(reverse("admin:cms_pageview_changelist"))

        self.assertEqual(response.status_code, 200)
        header = response["Content-Security-Policy"]
        nonce = re.search(r"'nonce-([^']+)'", header).group(1)
        html = response.content.decode()
        inline_scripts = [
            tag
            for tag in re.findall(r"<script\b[^>]*>", html, flags=re.IGNORECASE)
            if not re.search(r"\bsrc\s*=", tag, flags=re.IGNORECASE)
        ]
        style_elements = re.findall(r"<style\b[^>]*>", html, flags=re.IGNORECASE)

        self.assertTrue(inline_scripts)
        self.assertTrue(style_elements)
        self.assertTrue(all(f'nonce="{nonce}"' in tag for tag in [*inline_scripts, *style_elements]))
        self.assertNotRegex(html, r"\son[a-z]+\s*=\s*[\"']")
        self.assertIn("chart.js@4.5.1/", html)
        self.assertIn("chartjs-plugin-datalabels@2.2.0/", html)

    def test_change_form_contains_route_editor_config_with_page_id(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn("CMS_ROUTE_EDITOR", content)
        self.assertIn(str(self.page.pk), content)

    def test_change_form_includes_block_editor_script(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn("cms-block-editor.js", content)
        self.assertIn("block-editor/assets.js", content)
        self.assertIn("CMS_ASSET_MANAGER", content)

    def test_change_form_has_preview_button(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn("openLivePreview", content)
        self.assertIn("Preview", content)

    def test_inline_preview_panel_renders_outside_content_blocks_editor(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()

        preview_idx = content.index('id="cms-inline-preview"')
        editor_idx = content.index('class="visual-editor-wrapper"')
        blocks_idx = content.index('id="cms-blocks-container"')

        self.assertLess(preview_idx, editor_idx)
        self.assertLess(editor_idx, blocks_idx)

    def test_preview_store_endpoint_returns_token(self):
        url = reverse("admin:cms_cmspage_preview")
        payload = {
            "title": "Preview Test",
            "route": "/preview-test",
            "blocks": [{"block_type": "rich_text", "data": {"body": "<p>Hello</p>"}}],
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        self.assertTrue(len(data["token"]) > 0)

        # Verify the preview data was stored in cache
        cached = cache.get(f"cms:preview:{data['token']}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["title"], "Preview Test")

    def test_preview_store_endpoint_rejects_get(self):
        url = reverse("admin:cms_cmspage_preview")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_preview_store_endpoint_rejects_invalid_json(self):
        url = reverse("admin:cms_cmspage_preview")
        response = self.client.post(
            url,
            data="not-valid-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
