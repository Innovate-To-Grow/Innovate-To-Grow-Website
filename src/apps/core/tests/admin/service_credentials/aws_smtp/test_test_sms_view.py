from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.credentials import AwsCredentialsError
from apps.core.tests.admin.service_credentials.aws_smtp.test_test_send_mixin import _admin, _messages, _request
from apps.event.tests.helpers import make_superuser


class TestSmsViewTest(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.admin = _admin()

    def test_get_renders_form(self):
        request = _request("get", self.user, path="/admin/test-sms/")
        with patch.object(AWSCredentialConfig, "load", return_value=AWSCredentialConfig(name="AWS")):
            response = self.admin.test_sms_list_view(request)
        self.assertEqual(response.template_name, "admin/core/test_send_form.html")
        self.assertIn("Send Test SMS", response.context_data["title"])

    def test_post_missing_recipient_redirects_to_canonical_form(self):
        request = _request("post", self.user, {"recipient": ""}, path="//attacker.example")
        with patch.object(AWSCredentialConfig, "load", return_value=AWSCredentialConfig(name="AWS")):
            response = self.admin.test_sms_list_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:core_awscredentialconfig_test_sms"))
        self.assertIn("Please provide a phone number.", _messages(request))

    def test_post_missing_recipient_errors(self):
        request = _request("post", self.user, {"recipient": ""}, path="/admin/test-sms/")
        with patch.object(AWSCredentialConfig, "load", return_value=AWSCredentialConfig(name="AWS")):
            response = self.admin.test_sms_list_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("Please provide a phone number.", _messages(request))

    def test_post_success(self):
        request = _request(
            "post", self.user, {"country_code": "+1", "recipient": "2065551234"}, path="/admin/test-sms/"
        )
        with (
            patch.object(AWSCredentialConfig, "load", return_value=AWSCredentialConfig(name="AWS")),
            patch(
                "apps.core.admin.service_credentials.aws_smtp.test_send_mixin._send_test_sms",
                return_value="message (ID: m1)",
            ),
        ):
            self.admin.test_sms_list_view(request)
        self.assertTrue(any("Test SMS sent to +12065551234" in m for m in _messages(request)))

    def test_post_failure(self):
        request = _request(
            "post", self.user, {"country_code": "+1", "recipient": "2065551234"}, path="/admin/test-sms/"
        )
        with (
            patch.object(AWSCredentialConfig, "load", return_value=AWSCredentialConfig(name="AWS")),
            patch(
                "apps.core.admin.service_credentials.aws_smtp.test_send_mixin._send_test_sms",
                side_effect=RuntimeError("sms boom"),
            ),
        ):
            self.admin.test_sms_list_view(request)
        self.assertTrue(any("Failed to send test SMS: sms boom" in m for m in _messages(request)))

    def test_action_redirect(self):
        request = _request("get", self.user, path="/admin/test-sms/")
        response = self.admin.test_sms_list(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("test-sms", response.url)


class AwsCredentialsServiceTest(TestCase):
    def test_resolve_raises_when_unconfigured(self):
        from apps.core.services.aws.credentials import resolve_aws_credentials

        AWSCredentialConfig.objects.all().delete()
        with self.assertRaises(AwsCredentialsError):
            resolve_aws_credentials()

    def test_resolve_returns_credentials(self):
        from apps.core.services.aws.credentials import resolve_aws_credentials

        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="K", secret_access_key="S", default_region="eu-west-1"
        )
        creds = resolve_aws_credentials("ses")
        self.assertEqual(creds.access_key_id, "K")
        self.assertEqual(creds.region, "eu-west-1")

    def test_available_true_and_false(self):
        from apps.core.services.aws.credentials import aws_credentials_available

        AWSCredentialConfig.objects.all().delete()
        self.assertFalse(aws_credentials_available())
        AWSCredentialConfig.objects.create(name="AWS", is_active=True, access_key_id="K", secret_access_key="S")
        self.assertTrue(aws_credentials_available())
