from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from core.admin.service_credentials.aws import AWSCredentialConfigAdmin
from core.models import AWSCredentialConfig, GmailImportConfig
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


class AWSCredentialConfigAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            default_model_id="new.runtime-model-v1:0",
        )

    def _request(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        return request

    @patch("boto3.client")
    def test_bedrock_test_action_uses_runtime_without_catalog_precheck(self, mock_boto_client):
        mock_runtime = MagicMock()
        mock_runtime.converse.return_value = {"output": {"message": {"content": [{"text": "OK"}]}}}
        mock_boto_client.return_value = mock_runtime
        model_admin = AWSCredentialConfigAdmin(AWSCredentialConfig, AdminSite())

        with patch("core.services.bedrock.models.catalog.fetch_models_from_aws", side_effect=AssertionError):
            response = model_admin.test_bedrock_api(self._request(), str(self.config.pk))

        self.assertEqual(response.status_code, 302)
        mock_runtime.converse.assert_called_once()
        self.assertEqual(mock_runtime.converse.call_args.kwargs["modelId"], "new.runtime-model-v1:0")
