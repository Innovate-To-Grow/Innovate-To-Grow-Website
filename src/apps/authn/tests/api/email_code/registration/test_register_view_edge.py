from unittest.mock import patch

from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.core.services.aws.provider_outcomes import ProviderDeliveryError


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class RegisterViewEdgeTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_register_invalid_payload(self, _c, _s):
        resp = self.client.post("/authn/register/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_register_save_delivery_error_returns_503(self, _c, mock_send):
        mock_send.side_effect = ProviderDeliveryError("ses rejected", outcome="permanent")
        resp = self.client.post(
            "/authn/register/",
            {
                "email": "newbie@example.com",
                "password": "PlaintextPass123!",
                "password_confirm": "PlaintextPass123!",
                "first_name": "New",
                "last_name": "Bie",
                "organization": "Acme",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 503)

    def test_password_reset_verify_invalid_payload(self, _c, _s):
        resp = self.client.post("/authn/password-reset/verify-code/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
