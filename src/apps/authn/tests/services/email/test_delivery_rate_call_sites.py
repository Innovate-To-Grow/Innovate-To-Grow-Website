"""Account emails go through the delivery-rate limiter on the transactional lane, and a held-back sign-in code tells
the person when to try again."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email import (
    AuthChallengeDeliveryError,
    issue_email_challenge,
    send_admin_invitation_email,
    send_notification_email,
    send_verification_email,
)
from apps.authn.views.helpers import challenge_error_response
from apps.core.models import AWSCredentialConfig, DeliveryRateState, EmailServiceConfig
from apps.core.services.delivery_rates import Lane, ses_identity
from apps.core.tests.services.delivery_rates.helpers import FakeClock, spy_on_email_admissions
from apps.event.tests.helpers import make_member

SES_CLIENT = "apps.core.services.email.ses.boto3.client"


class AccountEmailCallSiteTests(TestCase):
    def setUp(self):
        self.clock = FakeClock(timezone.now()).install(self)
        self.aws = AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu")
        patcher = patch(SES_CLIENT)
        self.ses = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.ses.send_raw_email.return_value = {"MessageId": "ses-1"}
        self.admissions = spy_on_email_admissions(self)

    def assert_one_transactional_admission(self):
        self.assertEqual(self.admissions.call_count, 1)
        call = self.admissions.call_args
        self.assertEqual(call.args, ("ses_send", ses_identity(self.aws.pk, "us-west-2")))
        self.assertEqual(call.kwargs["lane"], Lane.TRANSACTIONAL)

    def test_sign_in_codes_are_admitted(self):
        send_verification_email(recipient="a@example.com", code="123456", purpose="login")

        self.assert_one_transactional_admission()

    def test_admin_invitations_are_admitted(self):
        invitation = SimpleNamespace(
            email="new@example.com",
            expires_at=timezone.now(),
            invited_by=None,
            message="",
            get_role_display=lambda: "Staff",
            get_acceptance_url=lambda request: "https://example.com/accept/token",
        )

        send_admin_invitation_email(invitation=invitation)

        self.assert_one_transactional_admission()

    def test_security_notices_are_admitted(self):
        with patch("apps.authn.services.email.send_email.senders.render_to_string", return_value="<p>Notice</p>"):
            self.assertTrue(
                send_notification_email(recipient="a@example.com", subject="Notice", template="x.html", context={})
            )

        self.assert_one_transactional_admission()

    def test_a_held_back_sign_in_code_says_when_to_try_again_and_keeps_no_challenge(self):
        member = make_member(email="held@example.com")
        DeliveryRateState.objects.create(
            channel="ses_send",
            identity=ses_identity(self.aws.pk, "us-west-2"),
            cooldown_group="ses:us-west-2",
            cooldown_until=self.clock.now() + timedelta(seconds=45),
        )

        with self.assertRaises(AuthChallengeDeliveryError) as caught:
            issue_email_challenge(member=member, purpose="login", target_email="held@example.com")

        self.assertEqual(caught.exception.retry_after, 45)
        self.assertEqual(
            str(caught.exception), "Email delivery is busy right now; please try again in about 45 seconds."
        )
        self.assertFalse(EmailAuthChallenge.objects.filter(member=member).exists())
        self.ses.send_raw_email.assert_not_called()

        response = challenge_error_response(caught.exception)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["retry_after"], 45)
        self.assertIn("about 45 seconds", response.data["detail"])
        self.assertEqual(response["Retry-After"], "45")

    def test_other_delivery_failures_keep_the_generic_answer(self):
        response = challenge_error_response(AuthChallengeDeliveryError(outcome="permanent"))

        self.assertEqual(response.data, {"detail": "Failed to send verification email."})
        self.assertFalse(response.has_header("Retry-After"))
