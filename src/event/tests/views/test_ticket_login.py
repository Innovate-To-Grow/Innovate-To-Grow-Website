from django.test import TestCase
from rest_framework.test import APIClient

from event.services.ticket_assets import build_ticket_login_token
from event.tests.helpers import make_member


class TicketAutoLoginViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()

    def test_empty_token_returns_400(self):
        response = self.client.post("/event/ticket-login/", {"token": ""}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Token is required.")

    def test_missing_token_returns_400(self):
        response = self.client.post("/event/ticket-login/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Token is required.")

    def test_invalid_token_returns_400(self):
        response = self.client.post("/event/ticket-login/", {"token": "garbage"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_valid_token_returns_200_with_jwt(self):
        token = build_ticket_login_token(self.member)
        response = self.client.post("/event/ticket-login/", {"token": token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_incomplete_profile_routes_to_complete_profile(self):
        self.member.first_name = ""
        self.member.last_name = ""
        self.member.save(update_fields=["first_name", "last_name", "updated_at"])
        token = build_ticket_login_token(self.member)

        response = self.client.post("/event/ticket-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_token_can_be_reused(self):
        token = build_ticket_login_token(self.member)

        first_response = self.client.post("/event/ticket-login/", {"token": token}, format="json")
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post("/event/ticket-login/", {"token": token}, format="json")
        self.assertEqual(second_response.status_code, 200)
        self.assertIn("access", second_response.data)

    def test_inactive_member_returns_400(self):
        token = build_ticket_login_token(self.member)
        self.member.is_active = False
        self.member.save()
        response = self.client.post("/event/ticket-login/", {"token": token}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_deleted_member_returns_400(self):
        token = build_ticket_login_token(self.member)
        self.member.delete()
        response = self.client.post("/event/ticket-login/", {"token": token}, format="json")
        self.assertEqual(response.status_code, 400)
