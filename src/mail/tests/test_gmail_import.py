import base64
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from mail.models import EmailCampaign
from mail.services.gmail_import import (
    DEFAULT_GMAIL_MAILBOX,
    GmailImportError,
    fetch_message_html_fragment,
    import_message_into_campaign,
    list_recent_sent_messages,
)
from mail.services.preview import HTML_MARKER, render_preview


def _encode_html(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


class _ExecuteCall:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeMessagesResource:
    def __init__(self, list_response, message_map):
        self.list_response = list_response
        self.message_map = message_map
        self.list_kwargs = None
        self.get_calls = []

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return _ExecuteCall(self.list_response)

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _ExecuteCall(self.message_map[kwargs["id"]])


class _FakeUsersResource:
    def __init__(self, messages_resource):
        self.messages_resource = messages_resource

    def messages(self):
        return self.messages_resource


class _FakeGmailService:
    def __init__(self, list_response, message_map):
        self.messages_resource = _FakeMessagesResource(list_response, message_map)

    def users(self):
        return _FakeUsersResource(self.messages_resource)


class GmailImportServiceTest(TestCase):
    def test_list_recent_sent_messages_returns_recent_sent_summaries(self):
        html_data = _encode_html("<html><body><p>Hello from Gmail</p></body></html>")
        service = _FakeGmailService(
            {"messages": [{"id": "msg-1"}]},
            {
                "msg-1": {
                    "id": "msg-1",
                    "snippet": "Recent snippet",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Recent Campaign"},
                            {"name": "Date", "value": "Mon, 06 Apr 2026 09:00:00 -0700"},
                        ],
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {
                                "mimeType": "text/html",
                                "body": {"data": html_data},
                            }
                        ],
                    },
                }
            },
        )

        with patch("mail.services.gmail_import._get_gmail_service", return_value=service):
            messages = list_recent_sent_messages(limit=5)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_id"], "msg-1")
        self.assertEqual(messages[0]["subject"], "Recent Campaign")
        self.assertEqual(messages[0]["snippet"], "Recent snippet")
        self.assertTrue(messages[0]["has_html"])
        self.assertEqual(
            service.messages_resource.list_kwargs,
            {"userId": "me", "labelIds": ["SENT"], "maxResults": 5},
        )

    def test_fetch_message_html_fragment_extracts_body_from_full_document(self):
        service = _FakeGmailService(
            {"messages": []},
            {
                "msg-1": {
                    "id": "msg-1",
                    "payload": {
                        "mimeType": "text/html",
                        "body": {
                            "data": _encode_html(
                                "<html><head><title>T</title></head><body><p>Hello <strong>world</strong></p></body></html>"
                            )
                        },
                    },
                }
            },
        )

        with patch("mail.services.gmail_import._get_gmail_service", return_value=service):
            fragment = fetch_message_html_fragment("msg-1")

        self.assertEqual(fragment, "<p>Hello <strong>world</strong></p>")

    def test_import_message_into_campaign_saves_html_marker(self):
        campaign = EmailCampaign.objects.create(subject="Campaign", body="Before import")

        with patch("mail.services.gmail_import.fetch_message_html_fragment", return_value="<p>Imported</p>"):
            import_message_into_campaign(campaign, "msg-1")

        campaign.refresh_from_db()
        self.assertEqual(campaign.body, HTML_MARKER + "<p>Imported</p>")

    def test_get_gmail_service_raises_when_google_credentials_missing(self):
        with patch(
            "mail.services.gmail_import.GoogleCredentialConfig.load",
            return_value=SimpleNamespace(is_configured=False),
        ):
            with self.assertRaises(GmailImportError):
                list_recent_sent_messages()

    def test_fetch_message_html_fragment_raises_when_html_missing(self):
        service = _FakeGmailService(
            {"messages": []},
            {
                "msg-1": {
                    "id": "msg-1",
                    "payload": {
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {
                                "mimeType": "text/plain",
                                "body": {"data": _encode_html("Only plain text")},
                            }
                        ],
                    },
                }
            },
        )

        with patch("mail.services.gmail_import._get_gmail_service", return_value=service):
            with self.assertRaises(GmailImportError):
                fetch_message_html_fragment("msg-1")

    def test_render_preview_wraps_imported_raw_html_without_escaping(self):
        campaign = Mock(subject="Preview", body=HTML_MARKER + "<p><strong>Imported</strong> HTML</p>")

        preview = render_preview(campaign)

        self.assertIn("Innovate to Grow", preview["html"])
        self.assertIn("<strong>Imported</strong>", preview["html"])
        self.assertNotIn("&lt;strong&gt;Imported", preview["html"])

    def test_get_gmail_service_uses_delegated_mailbox(self):
        delegated = object()
        base_credentials = Mock()
        base_credentials.with_subject.return_value = delegated

        with (
            patch(
                "mail.services.gmail_import.GoogleCredentialConfig.load",
                return_value=SimpleNamespace(
                    is_configured=True, get_credentials_info=lambda: {"client_email": "svc@test"}
                ),
            ),
            patch(
                "mail.services.gmail_import.service_account.Credentials.from_service_account_info",
                return_value=base_credentials,
            ) as mock_from_info,
            patch(
                "mail.services.gmail_import.build",
                return_value=object(),
            ) as mock_build,
        ):
            list_recent = None
            try:
                from mail.services.gmail_import import _get_gmail_service

                list_recent = _get_gmail_service(DEFAULT_GMAIL_MAILBOX)
            finally:
                self.assertIsNotNone(list_recent)

        mock_from_info.assert_called_once()
        base_credentials.with_subject.assert_called_once_with(DEFAULT_GMAIL_MAILBOX)
        mock_build.assert_called_once_with("gmail", "v1", credentials=delegated, cache_discovery=False)
