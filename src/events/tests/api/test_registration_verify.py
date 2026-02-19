"""
Tests for event registration submit, OTP verification, and status endpoints.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from authn.models import Member
from events.models import Event, EventQuestion, EventRegistration, EventTicketOption
from notify.models import VerificationRequest
from notify.services import VerificationError


class EventRegistrationVerifyTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = Member.objects.create_user(
            username="member-one",
            email="member1@example.com",
            password="pass1234",
            first_name="Old",
            last_name="Name",
        )
        self.event = Event.objects.create(
            event_name="Spring Demo",
            slug="spring-demo",
            event_date_time=timezone.now(),
            is_live=True,
            is_published=True,
        )
        self.ticket = EventTicketOption.objects.create(event=self.event, label="Attendee", order=1, is_active=True)
        self.question = EventQuestion.objects.create(
            event=self.event,
            prompt="Dietary restrictions?",
            order=1,
            required=False,
            is_active=True,
        )
        self.submit_url = reverse("events:event-registration-submit")
        self.verify_otp_url = reverse("events:event-registration-verify-otp")
        self.status_url = reverse("events:event-registration-status")

    def _create_link_token(self, token: str = "tok-123"):
        VerificationRequest.objects.create(
            channel=VerificationRequest.CHANNEL_EMAIL,
            method=VerificationRequest.METHOD_LINK,
            target=self.member.email,
            purpose="event_registration_link",
            token=token,
            expires_at=timezone.now() + timedelta(hours=1),
            max_attempts=5,
        )
        return token

    @patch("events.views.registration.issue_code")
    def test_submit_with_phone_subscribe_requests_otp(self, mock_issue_code):
        token = self._create_link_token("tok-otp")
        EventRegistration.objects.create(
            event=self.event,
            member=self.member,
            registration_token=token,
            source_email=self.member.email,
        )
        payload = {
            "token": token,
            "phone_number": "2095551234",
            "phone_region": "1-US",
            "phone_subscribed": True,
        }
        response = self.client.post(self.submit_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["otp_required"])

        registration = EventRegistration.objects.get(event=self.event, member=self.member)
        self.assertEqual(registration.status, EventRegistration.STATUS_OTP_PENDING)
        self.assertTrue(registration.otp_target_phone.startswith("+1"))
        mock_issue_code.assert_called_once()

    def test_verify_otp_failure_and_success(self):
        token = self._create_link_token("tok-verify")
        registration = EventRegistration.objects.create(
            event=self.event,
            member=self.member,
            registration_token=token,
            source_email=self.member.email,
            status=EventRegistration.STATUS_OTP_PENDING,
            otp_target_phone="+12095551234",
            phone_subscribed=True,
        )

        with patch("events.views.registration.verify_code", side_effect=VerificationError("bad code")):
            failed = self.client.post(self.verify_otp_url, {"token": token, "code": "000000"}, format="json")
        self.assertEqual(failed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(failed.data["code"], "invalid_otp")

        with patch("events.views.registration.verify_code", return_value=True):
            success = self.client.post(self.verify_otp_url, {"token": token, "code": "123456"}, format="json")
        self.assertEqual(success.status_code, status.HTTP_200_OK)
        self.assertTrue(success.data["phone_verified"])

        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.STATUS_COMPLETED)
        self.assertTrue(registration.phone_verified)

    def test_status_endpoint_and_legacy_status_route(self):
        token = self._create_link_token("tok-status")
        EventRegistration.objects.create(
            event=self.event,
            member=self.member,
            registration_token=token,
            source_email=self.member.email,
            status=EventRegistration.STATUS_COMPLETED,
            phone_verified=True,
            submitted_at=timezone.now(),
        )

        api_response = self.client.get(f"{self.status_url}?token={token}")
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["event_slug"], self.event.slug)
        self.assertTrue(api_response.data["phone_verified"])

        legacy_response = self.client.get(f"/membership/event-registration/status/{self.event.slug}/{token}")
        self.assertEqual(legacy_response.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy_response.data["event_name"], self.event.event_name)

        mismatch = self.client.get(f"/membership/event-registration/status/wrong-slug/{token}")
        self.assertEqual(mismatch.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(mismatch.data["code"], "event_not_found")
