from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail

Member = get_user_model()


class NewsArticleAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
            first_name="News",
            last_name="Admin",
        )
        ContactEmail.objects.get_or_create(
            member=self.admin, email_address="admin@test.com", defaults={"email_type": "primary", "verified": True}
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newsarticle_changelist"))
        self.assertEqual(resp.status_code, 200)
