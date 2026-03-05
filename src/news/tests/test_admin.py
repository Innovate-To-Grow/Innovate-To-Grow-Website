from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

Member = get_user_model()


class NewsAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            email="admin@test.com",
            username="admin",
            password="testpass123",
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:news_newsarticle_changelist"))
        self.assertEqual(resp.status_code, 200)

    @patch("news.admin.article.sync_news")
    def test_sync_button(self, mock_sync):
        mock_sync.return_value = {"created": 5, "updated": 2, "errors": []}
        resp = self.client.get(reverse("admin:news_newsarticle_sync"))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once()

    @patch("news.admin.article.sync_news")
    def test_sync_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["bad item"]}
        resp = self.client.get(reverse("admin:news_newsarticle_sync"))
        self.assertEqual(resp.status_code, 302)
