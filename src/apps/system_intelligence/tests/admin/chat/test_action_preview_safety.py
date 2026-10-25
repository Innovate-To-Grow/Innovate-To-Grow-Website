import json
import re

from django.test import override_settings
from django.urls import reverse

from apps.cms.models import CMSBlock, CMSPage
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.exceptions import ActionRequestError
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminActionTests(SystemIntelligenceAdminBase):
    @override_settings(FRONTEND_URL="https://frontend.example/")
    def test_action_preview_frames_each_block_and_posts_sanitized_data(self):
        page = CMSPage.objects.create(slug="security", route="/security", title="Security", status="draft")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>Old</p>"})

        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_cms_page_update(
                page_id=str(page.pk),
                blocks=[
                    {
                        "block_type": "rich_text",
                        "admin_label": '<img src=x onerror="alert(1)">',
                        "data": {
                            "heading": '<strong onclick="alert(1)">Unsafe Heading</strong>',
                            "body_html": '<p>Allowed <strong>safe</strong></p><script>alert("xss")</script>'
                            '<a href="javascript:evil()">bad</a>',
                        },
                    },
                    {
                        "block_type": "section_group",
                        "data": {
                            "sections": [
                                {
                                    "heading": "Section",
                                    "body_html": '<p>Section Body</p><script>alert("section")</script>',
                                }
                            ]
                        },
                    },
                    {
                        "block_type": "faq_list",
                        "data": {
                            "items": [
                                {
                                    "question": "FAQ",
                                    "answer_html": '<p>Answer</p><a href="javascript:evil()">bad</a>',
                                }
                            ]
                        },
                    },
                ],
            )
        finally:
            actions.reset_action_context(tokens)

        response = self.client.get(
            reverse("admin:system_intelligence_action_preview", args=[payload["action_request"]["id"]])
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        frames = re.findall(
            r'<iframe class="si-action-preview-frame"[^>]*data-src="([^"]+)"\s+data-preview-nonce="([0-9a-f]+)"', html
        )
        self.assertEqual(len(frames), 3)
        for src, nonce in frames:
            self.assertEqual(src, f"https://frontend.example/_block-preview?nonce={nonce}")
        self.assertEqual(len({nonce for _, nonce in frames}), 3)
        # No frame loads before action-preview.js has its listeners in place.
        self.assertNotRegex(html, r"<iframe[^>]*\ssrc=\"")

        data = json.loads(re.search(r'<script id="si-action-preview-data"[^>]*>(.*?)</script>', html, re.S).group(1))
        self.assertEqual([entry["nonce"] for entry in data["blocks"]], [nonce for _, nonce in frames])
        rich_text, section_group, faq = (entry["block"] for entry in data["blocks"])
        self.assertEqual(rich_text["block_type"], "rich_text")
        self.assertIn("<strong>safe</strong>", rich_text["data"]["body_html"])
        self.assertIn("Section Body", section_group["data"]["sections"][0]["body_html"])
        self.assertIn("Answer", faq["data"]["items"][0]["answer_html"])
        for block in (rich_text, section_group, faq):
            serialized = json.dumps(block)
            self.assertNotIn("<script", serialized)
            self.assertNotIn("javascript:", serialized)

        # Labels and plain-text fields never reach the markup as HTML; the frames render the blocks.
        self.assertContains(response, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertNotContains(response, '<strong onclick="alert(1)">')
        self.assertNotContains(response, "<script>alert")
        self.assertNotContains(response, "/layout/styles.css")
        self.assertEqual(data["pageCssClass"], "")
        # The script carries the page's CSP nonce, the same one as its inline <style>.
        style_nonce = re.search(r'<style nonce="([^"]*)">', html).group(1)
        self.assertRegex(html, rf'<script src="[^"]*system_intelligence/js/action-preview\.js" nonce="{style_nonce}">')

    def test_action_preview_rejects_unsafe_link_list_hrefs(self):
        page = CMSPage.objects.create(slug="links", route="/links", title="Links", status="draft")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>Old</p>"})

        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            with self.assertRaises(ActionRequestError) as ctx:
                actions.propose_cms_page_update(
                    page_id=str(page.pk),
                    blocks=[
                        {
                            "block_type": "link_list",
                            "data": {
                                "items": [
                                    {"url": "javascript:alert(document.cookie)", "title": "Unsafe JS"},
                                    {"url": "data:text/html,<script>alert(1)</script>", "title": "Unsafe Data"},
                                    {"url": "java\nscript:alert(1)"},
                                    {"url": "//attacker.example/path", "title": "Scheme Relative"},
                                    {"url": "https://example.com/page", "title": "HTTPS"},
                                    {"url": "/about", "title": "Root Relative"},
                                    {"url": "relative/path", "title": "Relative"},
                                    {"url": "#section", "title": "Fragment"},
                                ]
                            },
                        }
                    ],
                )
            self.assertIn("unsafe scheme", str(ctx.exception).lower())
        finally:
            actions.reset_action_context(tokens)

    def test_cms_page_proposals_cannot_carry_page_css(self):
        page = CMSPage.objects.create(slug="css", route="/css", title="CSS", status="draft")

        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            with self.assertRaises(ActionRequestError) as ctx:
                actions.propose_cms_page_update(
                    page_id=str(page.pk),
                    page_fields={"page_css": '@import url("https://attacker.example/style.css");'},
                )
            self.assertEqual(str(ctx.exception), "Unsupported CMS page field: page_css")
        finally:
            actions.reset_action_context(tokens)

    def _propose_cms_update(self):
        page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            admin_label="Hero",
            data={"heading": "Hero", "body_html": "<p>Unchanged Hero</p>"},
        )
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=1, data={"body_html": "<p>Old</p>"})

        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            return actions.propose_cms_page_update(
                page_id=str(page.pk),
                blocks=[
                    {
                        "block_type": "rich_text",
                        "admin_label": "Hero",
                        "data": {"heading": "Hero", "body_html": "<p>Unchanged Hero</p>"},
                    },
                    {
                        "block_type": "rich_text",
                        "admin_label": "Intro",
                        "data": {"heading": "Updated", "heading_level": 2, "body_html": "<p>New Copy</p>"},
                    },
                ],
            )
        finally:
            actions.reset_action_context(tokens)
