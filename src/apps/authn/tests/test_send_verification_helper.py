"""Ensure automatic proofs never change unrelated test request semantics."""

from unittest.mock import patch

from django.http import QueryDict
from django.test import SimpleTestCase, override_settings
from django.test.client import Client
from rest_framework.test import APIClient

from apps.authn.tests import send_verification


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=True)
class AutoVerificationClientTests(SimpleTestCase):
    def test_raw_and_non_object_bodies_reach_both_clients_unchanged(self):
        bodies = ['{"message": "hello"}', "{invalid", b"\xff", [1, 2], [], 7, False]
        for client_type, original_name in (
            (APIClient, "_original_api_post"),
            (Client, "_original_django_post"),
        ):
            for path in ("/admin-api/records/", "/authn/email-auth/request-code/"):
                for body in bodies:
                    with self.subTest(client=client_type.__name__, path=path, body=body):
                        with (
                            patch.object(send_verification, original_name) as original,
                            patch.object(send_verification, "mint_send_verification") as mint,
                        ):
                            client_type().post(path, data=body, content_type="application/json")
                        self.assertIs(original.call_args.kwargs["data"], body)
                        self.assertEqual(original.call_args.kwargs["content_type"], "application/json")
                        mint.assert_not_called()

    def test_unrelated_mapping_body_reaches_original_client_unchanged(self):
        body = {"message": "hello"}
        with (
            patch.object(send_verification, "_original_api_post") as original,
            patch.object(send_verification, "mint_send_verification") as mint,
        ):
            APIClient().post("/admin-api/records/", data=body, format="json")
        self.assertIs(original.call_args.kwargs["data"], body)
        self.assertEqual(original.call_args.kwargs["format"], "json")
        mint.assert_not_called()

    def test_contact_challenge_context_does_not_mutate_callers_body(self):
        for body in ({"email": "member@example.com"}, QueryDict("email=member%40example.com")):
            with self.subTest(body_type=type(body).__name__):
                proof = {"verification_challenge_id": "challenge"}
                with (
                    patch.object(send_verification, "_original_api_post") as original,
                    patch.object(send_verification, "mint_send_verification", return_value=proof) as mint,
                ):
                    APIClient().post("/authn/contact-emails/contact-id/request-verification/", data=body)
                self.assertNotIn("contact_id", body)
                self.assertNotIn("verification_challenge_id", body)
                self.assertEqual(mint.call_args.args[2]["contact_id"], "contact-id")
                self.assertEqual(mint.call_args.args[2]["email"], "member@example.com")
                self.assertEqual(original.call_args.kwargs["data"]["email"], "member@example.com")
                self.assertEqual(original.call_args.kwargs["data"]["verification_challenge_id"], "challenge")
