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

    def test_membership_events_page_get_and_slug_mismatch(self):
        ready = self.client.get("/membership/events")
        self.assertEqual(ready.status_code, status.HTTP_200_OK)
        self.assertContains(ready, self.event.event_name)
        self.assertContains(ready, "Send Registration Link")

        ready_slug = self.client.get(f"/membership/events/{self.event.slug}")
        self.assertEqual(ready_slug.status_code, status.HTTP_200_OK)
        self.assertContains(ready_slug, self.event.event_name)

        mismatch = self.client.get("/membership/events/wrong-slug")
        self.assertEqual(mismatch.status_code, status.HTTP_404_NOT_FOUND)

    @patch("events.views.membership.issue_link")
    def test_membership_events_page_post(self, mock_issue_link):
        mock_issue_link.return_value = (
            SimpleNamespace(token="tok-legacy"),
            "https://example.com/membership/event-registration/spring-demo/tok-legacy",
        )
        response = self.client.post(f"/membership/events/{self.event.slug}", {"email": self.member.email})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Instructions sent")
        registration = EventRegistration.objects.get(event=self.event, member=self.member)
        self.assertEqual(registration.registration_token, "tok-legacy")

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

    def test_membership_event_registration_page_get(self):
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
        self.assertContains(get_response, self.event.event_name)
        self.assertContains(get_response, "Submit Registration")

    def test_membership_otp_page_get(self):
        response = self.client.get("/membership/otp/some-token?event_slug=spring-demo")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Verify Your Phone Number")

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
