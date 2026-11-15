from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from apps.core.admin.service_credentials.gmail import GmailAccessAccountAdmin
from apps.core.admin.service_credentials.google import GoogleCredentialConfigAdmin, GoogleCredentialConfigForm
from apps.core.models import (
    GmailAccessAccount,
    GoogleCredentialConfig,
)
from apps.core.tests.admin.service_credentials.aws_smtp.test_service_credentials_extra import (
    VALID_GOOGLE_JSON,
    _request,
)
from apps.event.tests.helpers import make_superuser


class GoogleAdminTest(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.admin = GoogleCredentialConfigAdmin(GoogleCredentialConfig, AdminSite())

    def test_status_badge(self):
        self.assertEqual(self.admin.status_badge(GoogleCredentialConfig(is_active=True)), ("Active", "success"))
        self.assertEqual(self.admin.status_badge(GoogleCredentialConfig(is_active=False)), ("Inactive", "danger"))

    def test_project_and_client_email_display(self):
        obj = GoogleCredentialConfig(credentials_json=VALID_GOOGLE_JSON)
        self.assertEqual(self.admin.project_id_display(obj), "proj-123")
        self.assertEqual(self.admin.client_email_display(obj), "svc@proj.iam.gserviceaccount.com")
        empty = GoogleCredentialConfig(credentials_json={})
        self.assertEqual(self.admin.project_id_display(empty), "—")
        self.assertEqual(self.admin.client_email_display(empty), "—")

    def test_activate_this_config(self):
        other = GoogleCredentialConfig.objects.create(name="Other", is_active=True, credentials_json=VALID_GOOGLE_JSON)
        target = GoogleCredentialConfig.objects.create(name="Target", credentials_json=VALID_GOOGLE_JSON)
        response = self.admin.activate_this_config(_request(self.user), str(target.pk))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(other.is_active)

    def test_has_delete_permission(self):
        active = GoogleCredentialConfig.objects.create(name="A", is_active=True, credentials_json=VALID_GOOGLE_JSON)
        inactive = GoogleCredentialConfig.objects.create(name="B", credentials_json=VALID_GOOGLE_JSON)
        self.assertFalse(self.admin.has_delete_permission(_request(self.user), active))
        self.assertTrue(self.admin.has_delete_permission(_request(self.user), inactive))

    def test_get_actions_removes_delete_selected(self):
        self.assertNotIn("delete_selected", self.admin.get_actions(_request(self.user)))


class GoogleFormTest(TestCase):
    def _file(self, content, name="key.json"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(name, content, content_type="application/json")

    def test_valid_json_file_parsed_into_credentials(self):
        import json

        form = GoogleCredentialConfigForm(
            data={"name": "Sheets", "credentials_json": "{}"},
            files={"credentials_file": self._file(json.dumps(VALID_GOOGLE_JSON).encode())},
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["credentials_json"], VALID_GOOGLE_JSON)

    def test_invalid_json_file_rejected(self):
        form = GoogleCredentialConfigForm(
            data={"name": "Sheets", "credentials_json": "{}"},
            files={"credentials_file": self._file(b"{not json")},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("credentials_file", form.errors)

    def test_non_object_json_rejected(self):
        import json

        form = GoogleCredentialConfigForm(
            data={"name": "Sheets", "credentials_json": "{}"},
            files={"credentials_file": self._file(json.dumps([1, 2, 3]).encode())},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("credentials_file", form.errors)

    def test_no_file_returns_none(self):
        form = GoogleCredentialConfigForm(
            data={"name": "Sheets", "credentials_json": __import__("json").dumps(VALID_GOOGLE_JSON)}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data.get("credentials_file"))


class GmailAdminTest(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.admin = GmailAccessAccountAdmin(GmailAccessAccount, AdminSite())

    def test_status_badge(self):
        self.assertEqual(self.admin.status_badge(GmailAccessAccount(is_active=True)), ("Active", "success"))
        self.assertEqual(self.admin.status_badge(GmailAccessAccount(is_active=False)), ("Inactive", "danger"))

    def test_activate_this_config(self):
        other = GmailAccessAccount.objects.create(name="Other", is_active=True, gmail_username="a@x.com")
        target = GmailAccessAccount.objects.create(name="Target", gmail_username="b@x.com")
        response = self.admin.activate_this_config(_request(self.user), str(target.pk))
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(other.is_active)

    def test_has_delete_permission(self):
        active = GmailAccessAccount.objects.create(name="A", is_active=True, gmail_username="a@x.com")
        inactive = GmailAccessAccount.objects.create(name="B", gmail_username="b@x.com")
        self.assertFalse(self.admin.has_delete_permission(_request(self.user), active))
        self.assertTrue(self.admin.has_delete_permission(_request(self.user), inactive))

    def test_get_actions_removes_delete_selected(self):
        self.assertNotIn("delete_selected", self.admin.get_actions(_request(self.user)))
