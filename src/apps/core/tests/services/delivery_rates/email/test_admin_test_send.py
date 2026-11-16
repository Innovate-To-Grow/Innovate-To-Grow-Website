from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services import delivery_rates as rates
from apps.core.tests.services.delivery_rates.email.test_email_facade import SES_CLIENT

from ..helpers import FakeClock, spy_on_email_admissions


class AdminTestSendTests(TestCase):
    def setUp(self):
        FakeClock().install(self)
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        self.config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu"
        )

    @patch(SES_CLIENT)
    def test_the_admin_test_email_is_admitted_on_the_transactional_lane(self, factory):
        from apps.core.admin.service_credentials.helpers import _send_test_email

        factory.return_value.send_raw_email.return_value = {"MessageId": "ses-1"}
        admissions = spy_on_email_admissions(self)

        self.assertEqual(_send_test_email(config=self.config, recipient="me@example.edu"), "AWS SES")
        self.assertEqual(admissions.call_args.kwargs["lane"], rates.Lane.TRANSACTIONAL)
