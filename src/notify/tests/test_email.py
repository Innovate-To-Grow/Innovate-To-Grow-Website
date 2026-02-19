"""
Tests for email layout rendering and admin preview utilities.
"""

from django.test import SimpleTestCase, TestCase

from ..admin.layout.utils import _highlight_values, _inject_preview_style
from ..models import EmailLayout, EmailMessageLayout
from ..providers.email import render_email_layout


class EmailLayoutRenderTest(TestCase):
    def test_render_email_layout_uses_default_layout(self):
        EmailLayout.objects.update(is_default=False)
        EmailLayout.objects.create(
            key="custom",
            name="Custom Layout",
            html_template="<html><head></head><body><div>Custom {{ body_html }}</div></body></html>",
            is_active=True,
            is_default=True,
        )

        html_body, text_body = render_email_layout(
            subject="Test Subject",
            body="Hello",
            context={"brand_name": "Test Brand"},
        )

        self.assertIn("Custom", html_body)
        self.assertIn("<p>Hello</p>", html_body)
        self.assertIn("Hello", text_body)

    def test_render_email_layout_uses_layout_key(self):
        EmailLayout.objects.create(
            key="custom-key",
            name="Custom Key Layout",
            html_template="<html><head></head><body><div>Keyed {{ body_html }}</div></body></html>",
            is_active=True,
            is_default=False,
        )

        html_body, _ = render_email_layout(
            subject="Keyed",
            body="Content",
            context={"brand_name": "Test Brand"},
            layout_key="custom-key",
        )

        self.assertIn("Keyed", html_body)
        self.assertIn("<p>Content</p>", html_body)


class EmailMessageLayoutRenderTest(TestCase):
    def test_email_message_layout_renders_with_recipient_name(self):
        layout = EmailMessageLayout.objects.create(
            key="welcome",
            name="Welcome",
            subject_template="Hi {{ recipient_name }}",
            preheader_template="Welcome {{ recipient_name }}",
            body_template="<p>Hello {{ recipient_name }}</p>",
            default_context={},
            is_active=True,
        )

        subject, body, preheader, context = layout.render(recipient_email="alice.smith@example.com")
        self.assertEqual(subject, "Hi Alice Smith")
        self.assertEqual(preheader, "Welcome Alice Smith")
        self.assertIn("Hello Alice Smith", body)
        self.assertEqual(context.get("recipient_name"), "Alice Smith")

    def test_email_message_layout_allows_override_context(self):
        layout = EmailMessageLayout.objects.create(
            key="override",
            name="Override",
            subject_template="Hi {{ recipient_name }}",
            preheader_template="Hello {{ recipient_name }}",
            body_template="<p>Hello {{ recipient_name }}</p>",
            default_context={},
            is_active=True,
        )

        subject, body, preheader, context = layout.render(
            context={"recipient_name": "Zoe"},
            recipient_email="user@example.com",
        )
        self.assertEqual(subject, "Hi Zoe")
        self.assertEqual(preheader, "Hello Zoe")
        self.assertIn("Hello Zoe", body)
        self.assertEqual(context.get("recipient_name"), "Zoe")


class AdminPreviewHighlightTest(SimpleTestCase):
    def test_highlight_values_in_preview_html(self):
        html = (
            "<html><head></head><body>"
            "<p>Hello Alice</p>"
            '<a href="mailto:alice@example.com">alice@example.com</a>'
            "</body></html>"
        )
        highlighted = _highlight_values(html, ["Alice", "alice@example.com"])
        self.assertIn('href="mailto:alice@example.com"', highlighted)
        self.assertIn('<span class="preview-highlight">Alice</span>', highlighted)
        self.assertIn('<span class="preview-highlight">alice@example.com</span>', highlighted)

    def test_inject_preview_style(self):
        html = "<html><head></head><body><p>Test</p></body></html>"
        styled = _inject_preview_style(html)
        self.assertIn(".preview-highlight", styled)
