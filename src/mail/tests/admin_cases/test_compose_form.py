"""Tests for mail app admin views."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from mail.forms import ComposeForm

Member = get_user_model()

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


@override_settings(ROOT_URLCONF="mail.tests.urls")
class ComposeFormTest(TestCase):
    """Tests for ComposeForm validation."""

    def test_valid_compose(self):
        form = ComposeForm(
            data={
                "recipient_source": "manual",
                "to": "user@example.com",
                "subject": "Test",
                "body": "<p>Hello</p>",
            }
        )
        self.assertTrue(form.is_valid())
