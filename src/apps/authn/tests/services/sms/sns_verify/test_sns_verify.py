from django.test import TestCase, override_settings

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ResolveAwsCredentialsTest(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.all().delete()
        EmailServiceConfig.objects.all().delete()

    def test_returns_active_aws_credential_config(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-east-1",
        )

        creds = resolve_aws_credentials("ses")

        self.assertEqual(creds.access_key_id, "aws-key")
        self.assertEqual(creds.region, "us-east-1")

    def test_all_services_share_the_same_region(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-east-1",
        )

        self.assertEqual(resolve_aws_credentials("ses").region, "us-east-1")
        self.assertEqual(resolve_aws_credentials("sns").region, "us-east-1")
        self.assertEqual(resolve_aws_credentials("bedrock").region, "us-east-1")

    def test_raises_when_no_aws_credentials_even_if_email_exists(self):
        EmailServiceConfig.objects.create(name="Email", is_active=True)

        with self.assertRaises(AwsCredentialsError):
            resolve_aws_credentials()
