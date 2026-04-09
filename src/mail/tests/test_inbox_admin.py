from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from event.tests.helpers import make_superuser


class InboxAdminFragmentTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    @patch("mail.admin.inbox.list_inbox_messages")
    def test_inbox_fragment_force_refreshes_and_returns_html(self, mock_list):
        mock_list.return_value = [
            {
                "uid": "42",
                "from_name": "A",
                "from_email": "a@example.com",
                "subject": "Hi",
                "snippet": "Body",
                "date": "2026-01-01",
                "is_seen": True,
            }
        ]

        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=30, force_refresh=True)
        self.assertIn(b"Hi", response.content)
        self.assertIn(b'data-inbox-refresh', response.content)
