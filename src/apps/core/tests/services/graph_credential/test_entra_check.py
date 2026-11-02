"""The Entra certificate test: one token request with an in-memory key, classified and then discarded."""

import json

from django.test import SimpleTestCase

from apps.core.services.email.graph import auth
from apps.core.services.email.graph.credential import entra_check
from apps.core.services.email.graph.credential.entra_check import EntraCheckResult, check_certificate, classify
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, make_certificate
from apps.core.tests.services.graph_credential.helpers import entra_rejection
from apps.core.tests.services.test_email_graph import ACCESS_TOKEN, GraphFixtureMixin, token_response


class ClassifyTests(SimpleTestCase):
    def test_a_token_means_entra_accepts_the_certificate(self):
        self.assertEqual(classify(token_response()), EntraCheckResult(entra_check.OK))

    def test_outages_throttling_and_unreadable_tokens_are_unreachable(self):
        for response in (
            HttpResponse(200, {}, b"not json"),
            HttpResponse(408, {}, b""),
            HttpResponse(429, {}, b""),
            HttpResponse(500, {}, b""),
            HttpResponse(503, {}, b""),
        ):
            with self.subTest(status=response.status):
                self.assertEqual(classify(response).outcome, entra_check.UNREACHABLE)

    def test_documented_aadsts_numbers_map_to_their_outcome(self):
        cases = {
            700027: entra_check.NOT_TRUSTED,
            700016: entra_check.WRONG_APP,
            90002: entra_check.WRONG_TENANT,
            7000112: entra_check.APP_DISABLED,
            7000215: entra_check.REJECTED,
        }
        for number, outcome in cases.items():
            with self.subTest(number):
                result = classify(entra_rejection(number))
                self.assertEqual(result, EntraCheckResult(outcome, f"invalid_client AADSTS{number}"))

    def test_a_rejection_without_a_readable_code_is_rejected(self):
        for body in (b"", b"[]", json.dumps({"error_description": "AADSTS700027: free text"}).encode()):
            with self.subTest(body=body):
                self.assertEqual(classify(HttpResponse(400, {}, body)).outcome, entra_check.REJECTED)

    def test_only_refusing_outcomes_block_a_change(self):
        refusing = {outcome for outcome in entra_check.DESCRIPTIONS if EntraCheckResult(outcome).refuses_change}

        self.assertEqual(
            refusing, {entra_check.WRONG_APP, entra_check.WRONG_TENANT, entra_check.APP_DISABLED, entra_check.REJECTED}
        )
        self.assertTrue(EntraCheckResult(entra_check.OK).accepted)
        self.assertFalse(EntraCheckResult(entra_check.NOT_TRUSTED).accepted)

    def test_descriptions_carry_only_the_allow_listed_code(self):
        result = classify(entra_rejection(700027))

        self.assertEqual(
            result.describe(),
            "Entra does not trust this certificate yet: it is not registered on the app. (invalid_client AADSTS700027)",
        )
        self.assertNotIn("free text", result.describe())


class CheckCertificateTests(GraphFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.certificate, self.key = make_certificate()

    def check(self):
        return check_certificate(tenant_id=TENANT_ID, client_id=CLIENT_ID, private_key=self.key, x5t_s256="x5t")

    def test_the_token_is_requested_once_and_never_cached(self):
        self.assertTrue(self.check().accepted)

        (request,) = self.fake.token_requests
        self.assertIn(b"client_assertion=", request.body)
        self.assertNotIn(ACCESS_TOKEN, repr(auth._cache))
        self.assertEqual(auth._cache, {})

    def test_transport_failures_are_unreachable(self):
        for failure in (ConnectFailed(), ConnectFailed(verification_failed=True), ResponseLost()):
            with self.subTest(failure=failure):
                self.script(token=failure)
                self.assertEqual(self.check().outcome, entra_check.UNREACHABLE)
