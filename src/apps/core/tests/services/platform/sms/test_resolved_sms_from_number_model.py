from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.models import AWSCredentialConfig


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ResolvedSmsFromNumberModelTest(TestCase):
    def setUp(self):
        cache.clear()
        AWSCredentialConfig.objects.all().delete()

    def test_manual_override_takes_precedence(self):
        config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            sms_from_number="+12065550000",
        )
        with patch("apps.core.services.aws.sms.resolve_origination_number") as mock_resolve:
            self.assertEqual(config.resolved_sms_from_number(), "+12065550000")
            mock_resolve.assert_not_called()

    @patch("apps.core.services.aws.sms.resolve_origination_number", return_value="+18667724739")
    def test_falls_back_to_auto_resolved_number(self, _mock_resolve):
        config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
        )
        self.assertEqual(config.resolved_sms_from_number(), "+18667724739")

    def test_empty_when_not_configured(self):
        config = AWSCredentialConfig()
        self.assertEqual(config.resolved_sms_from_number(), "")
