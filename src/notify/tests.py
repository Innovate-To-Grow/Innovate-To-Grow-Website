from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .admin.utils import _highlight_values, _inject_preview_style
from .models import EmailLayout, EmailMessageLayout, NotificationLog, VerificationRequest
from .providers.email import render_email_layout
from .services import issue_link


class NotifyAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_request_code_and_verify(self):
        request_url = reverse("notify:request-code")
        payload = {"channel": "email", "target": "user@example.com", "purpose": "contact_verification"}

        response = self.client.post(request_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        verification = VerificationRequest.objects.get(target="user@example.com")
        verify_url = reverse("notify:verify-code")
        verify_payload = {
            "channel": "email",
            "target": "user@example.com",
            "purpose": "contact_verification",
            "code": verification.code,
        }
        verify_response = self.client.post(verify_url, verify_payload, format="json")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

        verification.refresh_from_db()
        self.assertEqual(verification.status, VerificationRequest.STATUS_VERIFIED)

    def test_rate_limit_enforced(self):
        request_url = reverse("notify:request-code")
        payload = {"channel": "sms", "target": "+1234567890", "purpose": "contact_verification"}

        for _ in range(5):
            resp = self.client.post(request_url, payload, format="json")
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        sixth = self.client.post(request_url, payload, format="json")
        self.assertEqual(sixth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_verify_link(self):
        verification, token_url = issue_link(
            channel="email",
            target="link@example.com",
            purpose="contact_verification",
            base_url="http://example.com/verify",
        )

        token = verification.token
        verify_url = reverse("notify:verify-link", kwargs={"token": token})
        resp = self.client.get(verify_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        verification.refresh_from_db()
        self.assertEqual(verification.status, VerificationRequest.STATUS_VERIFIED)

    def test_send_notification(self):
        send_url = reverse("notify:send-notification")
        payload = {
            "channel": "email",
            "target": "notify@example.com",
            "subject": "Hello",
            "message": "Test notification",
        }
        resp = self.client.post(send_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        log = NotificationLog.objects.get(target="notify@example.com")
        self.assertEqual(log.status, NotificationLog.STATUS_SENT)


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
            "<a href=\"mailto:alice@example.com\">alice@example.com</a>"
            "</body></html>"
        )
        highlighted = _highlight_values(html, ["Alice", "alice@example.com"])
        self.assertIn("href=\"mailto:alice@example.com\"", highlighted)
        self.assertIn('<span class="preview-highlight">Alice</span>', highlighted)
        self.assertIn('<span class="preview-highlight">alice@example.com</span>', highlighted)

    def test_inject_preview_style(self):
        html = "<html><head></head><body><p>Test</p></body></html>"
        styled = _inject_preview_style(html)
        self.assertIn(".preview-highlight", styled)
