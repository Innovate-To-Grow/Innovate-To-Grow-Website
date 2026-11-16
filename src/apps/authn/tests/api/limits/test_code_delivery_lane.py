"""Outbound alignment: a verification code a person asked for goes out on the TRANSACTIONAL lane of the delivery-rate
control, end to end from the HTTP request to the provider call (email through the configured provider, SMS through
AWS End User Messaging), so it is never queued behind a bulk campaign; and a code request whose proof fails is not
promoted: nothing reaches the delivery-rate control or the provider."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail, Member
from apps.authn.services.send_verification.rules.constants import (
    FIELD_PAYLOAD,
    OP_EMAIL_AUTH_REQUEST_CODE,
    OP_PHONE_AUTH_REQUEST_CODE,
)
from apps.authn.tests.send_verification import mint_send_verification
from apps.core.models import AWSCredentialConfig, DeliveryRatePolicy, EmailServiceConfig
from apps.core.services import delivery_rates as rates
from apps.core.services.aws import sms_send
from apps.core.services.email import delivery
from apps.core.tests.services.delivery_rates.helpers import FakeClock, set_policy

Channel = DeliveryRatePolicy.Channel
SES_CLIENT = "apps.core.services.email.ses.boto3.client"
EMAIL = "member@example.com"
PHONE = "2025550123"
# 0.5 recipients a second: one transactional slot every 2 s, campaigns every 2.5 s (the transactional reserve).
SLOW = Decimal("0.5")


def record_admissions(test, module):
    """Wrap ``module.admit``: every call's lane and the admission it returned."""
    calls = []
    real = module.admit

    def admit(*args, **kwargs):
        admission = real(*args, **kwargs)
        calls.append((kwargs.get("lane", rates.Lane.TRANSACTIONAL), admission))
        return admission

    patcher = patch.object(module, "admit", side_effect=admit)
    patcher.start()
    test.addCleanup(patcher.stop)
    return calls


def queue_campaign(channel, identity, slots=2):
    """A bulk campaign holding the next ``slots`` campaign slots (as a worker sending one would)."""
    with rates.wait_mode(rates.WaitMode.WORKER):
        for _ in range(slots):
            rates.admit(channel, identity, lane=rates.Lane.BULK, budget_cost=1, message_cost=1)


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
    SEND_VERIFICATION_SMS_DAILY_LIMIT=1000,
)
class CodeDeliveryLaneTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = FakeClock().install(self)
        self.client = APIClient()
        self.member = Member.objects.create_user(email=EMAIL, password="Pass-123456!", is_active=True)
        ContactEmail.objects.filter(member=self.member).update(verified=True)
        aws = AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu")
        self.ses_identity = rates.ses_identity(aws.pk, "us-west-2")
        patcher = patch(SES_CLIENT)
        self.ses = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.ses.send_raw_email.return_value = {"MessageId": "ses-1"}

    def assert_ahead_of_the_campaign(self, admission):
        # The campaign really holds the next slots (the code waits a little), yet behind its two slots the code
        # would wait 5 s: the transactional reserve gives it the next transactional slot instead.
        self.assertGreater(admission.wait_seconds, 0)
        self.assertLessEqual(admission.wait_seconds, 2.5)

    def request_email_code(self, proof=None):
        proof = proof or mint_send_verification(self.client, OP_EMAIL_AUTH_REQUEST_CODE, {"email": EMAIL})
        return self.client.post("/authn/email-auth/request-code/", {"email": EMAIL, **proof}, format="json")

    def test_a_requested_email_code_is_sent_on_the_transactional_lane_ahead_of_a_campaign(self):
        set_policy(Channel.SES_SEND, smart_enabled=False, manual_rate=SLOW)
        queue_campaign(Channel.SES_SEND, self.ses_identity)
        admissions = record_admissions(self, delivery)

        response = self.request_email_code()

        self.assertIn(response.status_code, (200, 202), response.data)
        self.assertEqual([lane for lane, _admission in admissions], [rates.Lane.TRANSACTIONAL])
        self.assert_ahead_of_the_campaign(admissions[0][1])
        self.ses.send_raw_email.assert_called_once()

    def test_a_code_request_with_a_failed_proof_reaches_no_provider(self):
        admissions = record_admissions(self, delivery)
        proof = mint_send_verification(self.client, OP_EMAIL_AUTH_REQUEST_CODE, {"email": EMAIL})
        tampered = {**proof, FIELD_PAYLOAD: proof[FIELD_PAYLOAD][:-8] + "AAAAAAA="}

        response = self.request_email_code(tampered)

        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(admissions, [])
        self.ses.send_raw_email.assert_not_called()

    def test_a_requested_sms_code_is_sent_on_the_transactional_lane_ahead_of_a_campaign(self):
        aws_config = SimpleNamespace(
            region="us-west-2",
            render_sms_otp_message=lambda code: f"Code: {code}",
            resolved_sms_from_number=lambda: "+12065550000",
        )
        identity = sms_send.SmsSender(region="us-west-2", origination="+12065550000").identity
        set_policy(Channel.SMS_SEND, smart_enabled=False, manual_rate=SLOW)
        queue_campaign(Channel.SMS_SEND, identity)
        admissions = record_admissions(self, sms_send)
        client = MagicMock()
        client.send_text_message.return_value = {"MessageId": "sms-1"}
        proof = mint_send_verification(self.client, OP_PHONE_AUTH_REQUEST_CODE, {"phone_number": PHONE})

        with (
            patch("apps.authn.services.sms.sns_verify._assert_configured", return_value=aws_config),
            patch.object(sms_send, "_client", return_value=client),
        ):
            response = self.client.post(
                "/authn/phone-auth/request-code/", {"phone_number": PHONE, **proof}, format="json"
            )

        self.assertIn(response.status_code, (200, 202), response.data)
        self.assertEqual([lane for lane, _admission in admissions], [rates.Lane.TRANSACTIONAL])
        self.assert_ahead_of_the_campaign(admissions[0][1])
        client.send_text_message.assert_called_once()
        self.assertEqual(client.send_text_message.call_args.kwargs["MessageType"], "TRANSACTIONAL")
