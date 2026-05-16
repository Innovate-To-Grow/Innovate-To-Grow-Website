from django.urls import reverse

from cms.models import CMSBlock, CMSPage
from system_intelligence.services import actions
from system_intelligence.services.actions.exceptions import ActionRequestError
from system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminActionTests(SystemIntelligenceAdminBase):
    def test_action_preview_sanitizes_html_fragments_and_escapes_labels(self):
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
                                    "answer": '<p>Answer</p><a href="javascript:evil()">bad</a>',
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
        self.assertContains(response, "<strong>safe</strong>", html=True)
        self.assertContains(response, "Section Body")
        self.assertContains(response, "Answer")
        self.assertContains(response, "&lt;strong onclick=&quot;alert(1)&quot;&gt;Unsafe Heading&lt;/strong&gt;")
        self.assertContains(response, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")
        self.assertNotContains(response, "<script")
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertNotContains(response, '<strong onclick="alert(1)">')
        self.assertNotContains(response, "javascript:")

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

    def test_action_preview_does_not_render_ai_controlled_page_css(self):
        page = CMSPage.objects.create(slug="css", route="/css", title="CSS", status="draft")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>Old</p>"})

        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_cms_page_update(
                page_id=str(page.pk),
                page_fields={
                    "page_css": '@import url("https://attacker.example/style.css"); '
                    'body { background: url("https://attacker.example/x"); }'
                },
                blocks=[
                    {
                        "block_type": "rich_text",
                        "data": {"heading": "Updated", "body_html": "<p>New Copy</p>"},
                    }
                ],
            )
        finally:
            actions.reset_action_context(tokens)

        response = self.client.get(
            reverse("admin:system_intelligence_action_preview", args=[payload["action_request"]["id"]])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Copy")
        self.assertNotContains(response, "attacker.example")
        self.assertNotContains(response, "@import")

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
