"""
Tests for event registration API + legacy membership-compatible routes.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
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


class EventRegistrationAPITest(TestCase):
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
        self.request_link_url = reverse("events:event-registration-request-link")
        self.form_url = reverse("events:event-registration-form")
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

    def test_request_link_returns_not_found_for_unknown_member(self):
        response = self.client.post(self.request_link_url, {"email": "missing@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "member_not_found")

    @patch("events.views.registration.issue_link")
    def test_request_link_sends_and_persists_registration_token(self, mock_issue_link):
        mock_issue_link.return_value = (
            SimpleNamespace(token="tok-generated"),
            "https://example.com/membership/event-registration/spring-demo/tok-generated",
        )
        response = self.client.post(self.request_link_url, {"email": self.member.email}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "sent")
        registration = EventRegistration.objects.get(event=self.event, member=self.member)
        self.assertEqual(registration.registration_token, "tok-generated")

    def test_legacy_membership_events_get_and_slug_mismatch(self):
        ready = self.client.get("/membership/events")
        self.assertEqual(ready.status_code, status.HTTP_200_OK)
        self.assertEqual(ready.data["event_slug"], self.event.slug)

        ready_slug = self.client.get(f"/membership/events/{self.event.slug}")
        self.assertEqual(ready_slug.status_code, status.HTTP_200_OK)

        mismatch = self.client.get("/membership/events/wrong-slug")
        self.assertEqual(mismatch.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(mismatch.data["code"], "event_not_found")

    @patch("events.views.registration.issue_link")
    def test_legacy_membership_events_post(self, mock_issue_link):
        mock_issue_link.return_value = (
            SimpleNamespace(token="tok-legacy"),
            "https://example.com/membership/event-registration/spring-demo/tok-legacy",
        )
        response = self.client.post(f"/membership/events/{self.event.slug}", {"email": self.member.email}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["event_slug"], self.event.slug)

    def test_form_endpoint_with_token(self):
        token = self._create_link_token("tok-form")
        EventRegistration.objects.create(
            event=self.event,
            member=self.member,
            registration_token=token,
            source_email=self.member.email,
        )

        response = self.client.get(f"{self.form_url}?token={token}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["event"]["slug"], self.event.slug)
        self.assertEqual(len(response.data["schema"]["ticket_options"]), 1)
        self.assertEqual(len(response.data["schema"]["questions"]), 1)

    def test_legacy_event_registration_get_and_post(self):
        token = self._create_link_token("tok-legacy-form")
        EventRegistration.objects.create(
            event=self.event,
            member=self.member,
            registration_token=token,
            source_email=self.member.email,
        )
        path = f"/membership/event-registration/{self.event.slug}/{token}"

        get_response = self.client.get(path)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["event"]["event_name"], self.event.event_name)

        post_payload = {
            "first_name": "New",
            "last_name": "Member",
            "secondary_email": "secondary@example.com",
            "primary_email_subscribed": True,
            "secondary_email_subscribed": True,
            "ticket_option_id": str(self.ticket.id),
            "answers": [{"question_id": str(self.question.id), "answer_text": "None"}],
        }
        post_response = self.client.post(path, post_payload, format="json")
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)
        self.assertEqual(post_response.data["status"], EventRegistration.STATUS_COMPLETED)
        self.assertFalse(post_response.data["otp_required"])

        registration = EventRegistration.objects.get(event=self.event, member=self.member)
        self.assertEqual(registration.ticket_option_id, self.ticket.id)
        self.assertEqual(registration.answers.count(), 1)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "New")
        self.assertEqual(self.member.last_name, "Member")

    def test_submit_rejects_primary_email_change(self):
        token = self._create_link_token("tok-primary-lock")
        EventRegistration.objects.create(
            event=self.event,
            member=self.member,
            registration_token=token,
            source_email=self.member.email,
        )
        payload = {
            "token": token,
            "primary_email": "another@example.com",
        }
        response = self.client.post(self.submit_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "primary_email_locked")

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
            success = self.client.post(f"/membership/otp/{token}", {"code": "123456"}, format="json")
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
