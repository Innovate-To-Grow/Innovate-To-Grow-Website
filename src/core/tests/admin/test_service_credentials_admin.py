from django.test import TestCase
from django.urls import reverse

from core.models import GmailImportConfig
from event.tests.helpers import make_superuser


class GmailImportConfigAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = GmailImportConfig.objects.create(
            name="Primary Gmail Import",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )

    def test_changelist_shows_gmail_import_config(self):
        response = self.client.get(reverse("admin:core_gmailimportconfig_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary Gmail Import")
        self.assertContains(response, "campaigns@ucmerced.edu")

    def test_change_view_updates_gmail_import_config(self):
        response = self.client.post(
            reverse("admin:core_gmailimportconfig_change", args=[self.config.pk]),
            {
                "name": "Updated Gmail Import",
                "is_active": "on",
                "imap_host": "imap.gmail.com",
                "gmail_username": "updated@ucmerced.edu",
                "gmail_password": "new-app-password",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Updated Gmail Import")
        self.assertEqual(self.config.gmail_username, "updated@ucmerced.edu")
        self.assertEqual(self.config.gmail_password, "new-app-password")
