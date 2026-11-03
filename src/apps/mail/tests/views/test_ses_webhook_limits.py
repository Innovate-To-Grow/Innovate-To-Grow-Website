"""The SES webhook's limits: signed deliveries are counted only after the SNS signature is verified, rejected calls
in a bucket of their own, so unsigned junk never uses up the allowance of the real SNS deliveries; both rates are
fixed request-limit policies Smart limiting never tightens."""

import json
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.services.request_limits.scopes import classify_route
from apps.core.tests.request_limits.helpers import isolate, view_limit
from apps.mail.services.sns.signature import SnsVerificationError
from apps.mail.views.ses_webhook import SesEventThrottle, SesEventWebhookView, SesRejectedThrottle

URL = "/mail/ses/events/"
VERIFY = "apps.mail.views.ses_webhook.verify_sns_message"
PROCESS = "apps.mail.views.ses_webhook.process_sns_envelope"
SNS_IP = "54.240.0.10"
JUNK_IP = "198.51.100.66"
ENVELOPE = {"Type": "Notification", "MessageId": "sns-1", "TopicArn": "arn:aws:sns:us-west-2:123:ses-events"}


def signature_check(junk_ips=(JUNK_IP,)):
    """A verify_sns_message stand-in that rejects calls from ``junk_ips`` (the test client's address)."""

    def verify(envelope, allowed_topic_arns):
        if envelope.get("from") in junk_ips:
            raise SnsVerificationError("bad signature")

    return verify


@override_settings(SES_SNS_TOPIC_ARN=ENVELOPE["TopicArn"])
@view_limit(**{"view-ses-events": (3, 60), "view-ses-rejected": (2, 60)})
class SesWebhookLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.client = APIClient()
        for target, kwargs in ((VERIFY, {"side_effect": signature_check()}), (PROCESS, {})):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, ip, body=None):
        payload = json.dumps(body if body is not None else {**ENVELOPE, "from": ip})
        return self.client.post(URL, data=payload, content_type="application/json", REMOTE_ADDR=ip)

    def test_unsigned_junk_never_uses_up_the_real_deliveries_allowance(self):
        junk = [self.post(JUNK_IP).status_code for _ in range(4)]
        real = [self.post(SNS_IP).status_code for _ in range(4)]

        # Rejected twice, then refused before any signature work; the SNS sender keeps its full 3.
        self.assertEqual(junk, [403, 403, 429, 429])
        self.assertEqual(real, [200, 200, 200, 429])

    def test_a_refused_junk_sender_is_refused_before_the_signature_check(self):
        for _ in range(2):
            self.post(JUNK_IP)
        with patch(VERIFY) as verify:
            response = self.post(JUNK_IP)
        self.assertEqual(response.status_code, 429)
        verify.assert_not_called()
        self.assertGreater(int(response["Retry-After"]), 0)

    def test_malformed_bodies_count_as_rejected(self):
        statuses = [self.post(JUNK_IP, body=[1]).status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])

    def test_signed_deliveries_do_not_count_against_the_rejected_bucket(self):
        for _ in range(3):
            self.assertEqual(self.post(SNS_IP).status_code, 200)
        cache.clear()  # a fresh window for the signed bucket; the rejected one was never charged
        self.assertEqual(self.post(SNS_IP).status_code, 200)

    @override_settings(SES_SNS_TOPIC_ARN="")
    def test_an_unconfigured_webhook_charges_nobody(self):
        statuses = [self.post(SNS_IP).status_code for _ in range(4)]
        self.assertEqual(statuses, [503] * 4)

    @view_limit(**{"view-ses-rejected": None, "view-ses-events": None})
    def test_disabled_policies_limit_nothing(self):
        statuses = [self.post(JUNK_IP).status_code for _ in range(4)] + [self.post(SNS_IP).status_code]
        self.assertEqual(statuses, [403] * 4 + [200])


class SesWebhookPolicyTests(TestCase):
    def test_the_webhook_scope_and_its_limits_are_fixed_and_never_aggregated(self):
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        self.assertEqual(SesEventWebhookView.throttle_classes, [])
        self.assertEqual(classify_route(SesEventWebhookView.as_view(), "mail:ses-events", "POST").scope, "webhook-ses")
        self.assertTrue(scopes["webhook-ses"]["fixed"])
        # No aggregate cap: junk from many addresses cannot use up the real deliveries' share.
        self.assertIsNone(scopes["webhook-ses"]["global_cap"])
        for throttle, scope in ((SesEventThrottle, "view-ses-events"), (SesRejectedThrottle, "view-ses-rejected")):
            self.assertEqual(throttle.policy_scope, scope)
            self.assertTrue(scopes[scope]["fixed"])
            self.assertEqual(scopes[scope]["parent"], "webhook-ses")
        self.assertEqual(
            (scopes["view-ses-events"]["requests"], scopes["view-ses-events"]["period_seconds"]), (600, 60)
        )

    def test_record_without_a_counted_request_is_a_no_op(self):
        throttle = SesRejectedThrottle()
        throttle.record()  # allow_request never ran: nothing to count, no error
        self.assertFalse(hasattr(throttle, "history"))
