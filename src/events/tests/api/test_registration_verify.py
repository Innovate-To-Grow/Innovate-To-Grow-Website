"""
Tests for event registration submit and status endpoints.
"""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from authn.models import Member
from events.models import Event, EventQuestion, EventRegistration, EventTicketOption


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
        self.status_url = reverse("events:event-registration-status")

    def _create_registration_token(self, token: str | None = None):
        token = token or uuid.uuid4().hex
        registration, _ = EventRegistration.objects.get_or_create(
            event=self.event,
            member=self.member,
            defaults={
                "source_email": self.member.email,
                "status": EventRegistration.STATUS_PENDING,
            },
        )
        registration.registration_token = token
        registration.save(update_fields=["registration_token", "updated_at"])
        return token

    def test_submit_completes_registration(self):
        token = self._create_registration_token("tok-submit")
        payload = {
            "token": token,
            "phone_number": "2095551234",
            "phone_region": "1-US",
            "phone_subscribed": True,
        }
        response = self.client.post(self.submit_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["otp_required"])

        registration = EventRegistration.objects.get(event=self.event, member=self.member)
        self.assertEqual(registration.status, EventRegistration.STATUS_COMPLETED)
        self.assertTrue(registration.otp_target_phone.startswith("+1"))

    def test_status_endpoint_and_legacy_status_route(self):
        token = self._create_registration_token("tok-status")
        registration = EventRegistration.objects.get(event=self.event, member=self.member)
        registration.status = EventRegistration.STATUS_COMPLETED
        registration.phone_verified = True
        registration.submitted_at = timezone.now()
        registration.save()

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
