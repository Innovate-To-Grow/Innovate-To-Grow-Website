"""Tests for mail app admin views."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from mail.forms import GoogleAccountForm

Member = get_user_model()

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


@override_settings(ROOT_URLCONF="mail.tests.urls")
class GoogleAccountFormTest(TestCase):
    """Tests for GoogleAccountForm validation."""

    def test_valid_json(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": FAKE_SERVICE_JSON,
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid())

    def test_invalid_json(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": "not json",
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("service_account_json", form.errors)

    def test_missing_required_keys(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": '{"type":"service_account"}',
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Missing required keys", form.errors["service_account_json"][0])

    def test_wrong_type(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": '{"type":"authorized_user","project_id":"t","private_key":"k","client_email":"e"}',
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("service_account", form.errors["service_account_json"][0])
