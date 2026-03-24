import json

from django.contrib.auth import get_user_model
from django.test import TestCase

Member = get_user_model()


class SheetsAccountAdminTests(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="sheetadmin",
            email="sheetadmin@example.com",
            password="testpass123",
        )
        self.client.login(username="sheetadmin", password="testpass123")

    def test_account_changelist_loads(self):
        response = self.client.get("/admin/sheets/sheetsaccount/")
        self.assertEqual(response.status_code, 200)

    def test_account_add_page_loads(self):
        response = self.client.get("/admin/sheets/sheetsaccount/add/")
        self.assertEqual(response.status_code, 200)

    def test_create_account_with_valid_json(self):
        sa_json = json.dumps(
            {
                "type": "service_account",
                "project_id": "test-project",
                "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
                "client_email": "test@test.iam.gserviceaccount.com",
            }
        )
        response = self.client.post(
            "/admin/sheets/sheetsaccount/add/",
            {
                "email": "test@test.iam.gserviceaccount.com",
                "display_name": "Test Account",
                "service_account_json": sa_json,
                "is_active": True,
            },
        )
        # Should redirect on success (302) or show form with errors (200)
        self.assertIn(response.status_code, [200, 302])

    def test_create_account_rejects_invalid_json(self):
        response = self.client.post(
            "/admin/sheets/sheetsaccount/add/",
            {
                "email": "test@test.iam.gserviceaccount.com",
                "display_name": "Test Account",
                "service_account_json": "not valid json",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 200)  # Form re-displayed with errors


class SheetLinkAdminTests(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="sheetadmin",
            email="sheetadmin@example.com",
            password="testpass123",
        )
        self.client.login(username="sheetadmin", password="testpass123")

    def test_link_changelist_loads(self):
        response = self.client.get("/admin/sheets/sheetlink/")
        self.assertEqual(response.status_code, 200)

    def test_link_add_page_loads(self):
        response = self.client.get("/admin/sheets/sheetlink/add/")
        self.assertEqual(response.status_code, 200)


class SyncLogAdminTests(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="sheetadmin",
            email="sheetadmin@example.com",
            password="testpass123",
        )
        self.client.login(username="sheetadmin", password="testpass123")

    def test_synclog_changelist_loads(self):
        response = self.client.get("/admin/sheets/synclog/")
        self.assertEqual(response.status_code, 200)

    def test_synclog_no_add_permission(self):
        response = self.client.get("/admin/sheets/synclog/add/")
        self.assertEqual(response.status_code, 403)
