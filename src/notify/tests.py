from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import NotificationLog, VerificationRequest
from .services import issue_link


class NotifyAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_request_code_and_verify(self):
        request_url = reverse("notify:request-code")
        payload = {"channel": "email", "target": "user@example.com", "purpose": "contact_verification"}

        response = self.client.post(request_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        verification = VerificationRequest.objects.get(target="user@example.com")
        verify_url = reverse("notify:verify-code")
        verify_payload = {
            "channel": "email",
            "target": "user@example.com",
            "purpose": "contact_verification",
            "code": verification.code,
        }
        verify_response = self.client.post(verify_url, verify_payload, format="json")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

        verification.refresh_from_db()
        self.assertEqual(verification.status, VerificationRequest.STATUS_VERIFIED)

    def test_rate_limit_enforced(self):
        request_url = reverse("notify:request-code")
        payload = {"channel": "sms", "target": "+1234567890", "purpose": "contact_verification"}

        for _ in range(5):
            resp = self.client.post(request_url, payload, format="json")
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        sixth = self.client.post(request_url, payload, format="json")
        self.assertEqual(sixth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_verify_link(self):
        verification, token_url = issue_link(
            channel="email",
            target="link@example.com",
            purpose="contact_verification",
            base_url="http://example.com/verify",
        )

        token = verification.token
        verify_url = reverse("notify:verify-link", kwargs={"token": token})
        resp = self.client.get(verify_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        verification.refresh_from_db()
        self.assertEqual(verification.status, VerificationRequest.STATUS_VERIFIED)

    def test_send_notification(self):
        send_url = reverse("notify:send-notification")
        payload = {
            "channel": "email",
            "target": "notify@example.com",
            "subject": "Hello",
            "message": "Test notification",
        }
        resp = self.client.post(send_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        log = NotificationLog.objects.get(target="notify@example.com")
        self.assertEqual(log.status, NotificationLog.STATUS_SENT)
