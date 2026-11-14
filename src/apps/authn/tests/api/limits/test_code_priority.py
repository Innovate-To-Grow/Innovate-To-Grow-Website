"""Which code requests are promoted to P0: a signed-in member, or an anonymous request whose body carries a valid
send-verification proof for the challenge it names. Anything else is counted as unproven traffic."""

import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve
from rest_framework.test import APIClient

from apps.authn.services.send_verification.proofs import priority as proof_check
from apps.authn.services.send_verification.proofs.priority import carries_valid_proof
from apps.authn.services.send_verification.rules.constants import (
    FIELD_CHALLENGE_ID,
    FIELD_PAYLOAD,
    FIELD_REQUEST_ID,
    OP_EMAIL_AUTH_REQUEST_CODE,
)
from apps.authn.tests.send_verification import mint_send_verification
from apps.core.services.request_limits import priority, scopes
from apps.core.tests.request_limits.helpers import isolate

PATH = "/authn/email-auth/request-code/"
EMAIL = "someone@example.com"


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce", SEND_VERIFICATION_COST=10)
class CarriesValidProofTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.factory = RequestFactory()
        proof_check.forget_verdicts()
        self.addCleanup(proof_check.forget_verdicts)
        self.api = APIClient()
        self.proof = mint_send_verification(self.api, OP_EMAIL_AUTH_REQUEST_CODE, {"email": EMAIL})

    def request(self, body, content_type="application/json"):
        data = json.dumps(body) if content_type == "application/json" and not isinstance(body, str) else body
        return self.factory.post(PATH, data=data, content_type=content_type)

    def test_a_valid_proof_is_promoted(self):
        self.assertTrue(carries_valid_proof(self.request({"email": EMAIL, **self.proof})))

    def test_the_answer_is_the_challenge_id(self):
        # The limiter counts promotions per solved proof by this id (M1).
        found = carries_valid_proof(self.request({"email": EMAIL, **self.proof}))
        self.assertEqual(found, str(self.proof[FIELD_CHALLENGE_ID]))

    def test_a_replayed_body_is_verified_once(self):
        # M1: a replay flood costs neither the settings query nor the key derivation again.
        body = {"email": EMAIL, **self.proof}
        with patch.object(proof_check, "verify_payload", wraps=proof_check.verify_payload) as verify:
            results = {carries_valid_proof(self.request(body)) for _ in range(5)}
        self.assertEqual(results, {str(self.proof[FIELD_CHALLENGE_ID])})
        self.assertEqual(verify.call_count, 1)

    def test_a_verdict_is_forgotten_after_its_time_and_the_memory_is_bounded(self):
        body = {"email": EMAIL, **self.proof}
        with (
            patch.object(proof_check, "verify_payload", wraps=proof_check.verify_payload) as verify,
            patch.object(proof_check, "_now", side_effect=[0.0, proof_check.VERDICT_SECONDS + 1.0]),
        ):
            carries_valid_proof(self.request(body))
            carries_valid_proof(self.request(body))
        self.assertEqual(verify.call_count, 2)
        with patch.object(proof_check, "MAX_VERDICTS", 1):
            tampered = {**body, FIELD_PAYLOAD: self.proof[FIELD_PAYLOAD][:-8] + "AAAAAAA="}
            self.assertFalse(carries_valid_proof(self.request(tampered)))
            self.assertEqual(len(proof_check._VERDICTS), 1)

    def test_a_form_body_is_read_too(self):
        request = self.factory.post(PATH, data={"email": EMAIL, **self.proof})
        self.assertTrue(carries_valid_proof(request))

    def test_checking_spends_nothing_the_view_needs(self):
        request = self.request({"email": EMAIL, **self.proof})
        self.assertTrue(carries_valid_proof(request))
        self.assertTrue(carries_valid_proof(request))  # the body stays readable and the challenge unspent
        with patch("apps.authn.services.email.send_email.send_verification_email") as send:
            response = self.api.post(PATH, {"email": EMAIL, **self.proof}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        send.assert_called_once()

    def test_missing_fields_are_not_promoted(self):
        for field in (FIELD_CHALLENGE_ID, FIELD_PAYLOAD, FIELD_REQUEST_ID):
            with self.subTest(missing=field):
                body = {key: value for key, value in self.proof.items() if key != field}
                self.assertFalse(carries_valid_proof(self.request(body)))

    def test_a_tampered_payload_is_not_promoted(self):
        tampered = {**self.proof, FIELD_PAYLOAD: self.proof[FIELD_PAYLOAD][:-8] + "AAAAAAA="}
        self.assertFalse(carries_valid_proof(self.request(tampered)))

    def test_a_proof_for_another_challenge_is_not_promoted(self):
        other = {**self.proof, FIELD_CHALLENGE_ID: str(uuid.uuid4())}
        self.assertFalse(carries_valid_proof(self.request(other)))

    def test_unreadable_bodies_are_not_promoted(self):
        self.assertFalse(carries_valid_proof(self.request("{not json")))
        self.assertFalse(carries_valid_proof(self.request(json.dumps([1, 2]))))
        self.assertFalse(carries_valid_proof(self.factory.post(PATH)))
        request = self.request({"email": EMAIL, **self.proof})
        request.META["CONTENT_LENGTH"] = "nope"
        self.assertFalse(carries_valid_proof(request))

    def test_an_oversized_body_is_never_parsed(self):
        body = {"email": EMAIL, **self.proof, "padding": "x" * proof_check.MAX_BODY_BYTES}
        self.assertFalse(carries_valid_proof(self.request(body)))

    def test_a_body_already_read_as_a_stream_is_not_promoted(self):
        request = self.request({"email": EMAIL, **self.proof})
        request.read()
        self.assertFalse(carries_valid_proof(request))


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce", SEND_VERIFICATION_COST=10)
class CodeRequestClassificationTests(TestCase):
    """The authn app registers the check for the P0 code-send scope (``AuthnConfig.ready``)."""

    def setUp(self):
        cache.clear()
        isolate(self)
        proof_check.forget_verdicts()
        self.addCleanup(proof_check.forget_verdicts)
        self.factory = RequestFactory()

    def classify(self, body):
        request = self.factory.post(PATH, data=json.dumps(body), content_type="application/json")
        request.resolver_match = resolve(PATH)
        return scopes.classify(request, request.resolver_match.func)

    def test_the_check_is_registered_for_code_sends(self):
        self.assertEqual(
            priority.registered_checks()["auth-code-send"],
            "apps.authn.services.send_verification.proofs.priority.carries_valid_proof",
        )

    def test_a_user_initiated_request_is_p0_and_a_scripted_one_is_not(self):
        proof = mint_send_verification(APIClient(), OP_EMAIL_AUTH_REQUEST_CODE, {"email": EMAIL})
        self.assertEqual(self.classify({"email": EMAIL, **proof}).scope, "auth-code-send")
        self.assertEqual(self.classify({"email": EMAIL}), scopes.Classification("auth-code-unproven", None, "unproven"))

    def test_one_solved_proof_promotes_only_a_few_requests(self):
        # M1: replaying one solved ALTCHA body no longer lifts a whole flood into P0.
        proof = mint_send_verification(APIClient(), OP_EMAIL_AUTH_REQUEST_CODE, {"email": EMAIL})
        found = [self.classify({"email": EMAIL, **proof}).scope for _ in range(5)]
        self.assertEqual(found, ["auth-code-send"] * 3 + ["auth-code-unproven"] * 2)
        other = mint_send_verification(APIClient(), OP_EMAIL_AUTH_REQUEST_CODE, {"email": EMAIL})
        self.assertEqual(self.classify({"email": EMAIL, **other}).scope, "auth-code-send")
