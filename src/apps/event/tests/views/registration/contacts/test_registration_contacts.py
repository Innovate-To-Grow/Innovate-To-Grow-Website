"""Registration contact policy, proof ownership, and atomic persistence tests."""

import uuid
from datetime import timedelta
from itertools import product

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail, ContactPhone, EmailAuthChallenge
from apps.event.models import EventRegistration
from apps.event.tests.helpers import make_event, make_member, make_ticket


class _RegistrationContactPolicyCase(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="primary@example.com", first_name="Jane", last_name="Doe")
        self.client = APIClient()
        self.client.force_authenticate(self.member)
        self.email = "secondary@example.com"
        self.phone = "2095551234"

    def _post(self, event, **data):
        ticket = make_ticket(event)
        return self.client.post(
            "/event/registrations/",
            {
                "event_slug": event.slug,
                "ticket_id": str(ticket.pk),
                "attendee_first_name": "Jane",
                "attendee_last_name": "Doe",
                **data,
            },
            format="json",
        )

    def _event(self, **flags):
        return make_event(name=f"Contact policy {uuid.uuid4()}", registration_open=True, **flags)

    def _email_proof(self, event, **overrides):
        values = {
            "member": self.member,
            "purpose": EmailAuthChallenge.Purpose.EVENT_REGISTRATION,
            "target_email": self.email,
            "context_identifier": f"event-registration:{event.pk}",
            "verification_token_hash": make_password("test-registration-proof"),
            "status": EmailAuthChallenge.Status.VERIFIED,
            "verified_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=10),
        }
        values.update(overrides)
        return EmailAuthChallenge.objects.create(**values)

    def _proof_data(self, proof, **overrides):
        return {
            "attendee_secondary_email": self.email,
            "secondary_email_verification_challenge_id": str(proof.pk),
            "secondary_email_verification_token": "test-registration-proof",
            **overrides,
        }


class RegistrationContactPolicyTest(_RegistrationContactPolicyCase):
    def test_optional_and_required_contact_policy_matrix(self):
        for contact, verify, required, provided in product(
            ("phone", "email"), (False, True), (False, True), (False, True)
        ):
            with self.subTest(contact=contact, verify=verify, required=required, provided=provided):
                flags = (
                    {"collect_phone": True, "verify_phone": verify, "require_phone": required}
                    if contact == "phone"
                    else {
                        "allow_secondary_email": True,
                        "verify_secondary_email": verify,
                        "require_secondary_email": required,
                    }
                )
                event = self._event(**flags)
                field = "attendee_phone" if contact == "phone" else "attendee_secondary_email"
                value = self.phone if contact == "phone" else self.email
                response = self._post(event, **{field: value if provided else ""})
                rejected = (required and not provided) or (verify and provided)
                self.assertEqual(response.status_code, 400 if rejected else 201, response.data)
                self.assertEqual(EventRegistration.objects.filter(event=event).exists(), not rejected)
                if verify and provided:
                    expected_code = (
                        "phone_verification_required" if contact == "phone" else "secondary_email_verification_required"
                    )
                    self.assertEqual(response.data["code"], expected_code)
                elif required and not provided:
                    self.assertNotIn("code", response.data)

    def test_disabled_contacts_are_not_collected_or_synced(self):
        response = self._post(self._event(), attendee_secondary_email=self.email, attendee_phone=self.phone)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["attendee_secondary_email"], "")
        self.assertEqual(response.data["attendee_phone"], "")
        self.assertFalse(response.data["secondary_email_verified"])
        self.assertFalse(response.data["phone_verified"])
        self.assertFalse(ContactEmail.objects.filter(email_address=self.email).exists())
        self.assertFalse(ContactPhone.objects.filter(member=self.member).exists())

    def test_cleared_optional_email_stays_empty_even_with_profile_prefill(self):
        ContactEmail.objects.create(member=self.member, email_address=self.email, email_type="secondary", verified=True)
        response = self._post(
            self._event(allow_secondary_email=True, verify_secondary_email=True), attendee_secondary_email=""
        )
        self.assertEqual(response.status_code, 201)
        registration = EventRegistration.objects.get(pk=response.data["id"])
        self.assertEqual(registration.attendee_secondary_email, "")
        self.assertFalse(registration.secondary_email_verified)
        registration.save()
        registration.refresh_from_db()
        self.assertEqual(registration.attendee_secondary_email, "")

    def test_profile_contact_does_not_satisfy_missing_required_input(self):
        ContactEmail.objects.create(member=self.member, email_address=self.email, email_type="secondary", verified=True)
        event = self._event(allow_secondary_email=True, require_secondary_email=True)
        self.assertEqual(self._post(event).status_code, 400)

    def test_validated_profile_contacts_can_be_reused_with_or_without_verification_requirement(self):
        ContactEmail.objects.create(member=self.member, email_address=self.email, email_type="secondary", verified=True)
        ContactPhone.objects.create(member=self.member, phone_number=self.phone, region="1-US", verified=True)
        for verify in (False, True):
            with self.subTest(verify=verify):
                event = self._event(
                    allow_secondary_email=True,
                    verify_secondary_email=verify,
                    require_secondary_email=True,
                    collect_phone=True,
                    verify_phone=verify,
                    require_phone=True,
                )
                response = self._post(event, attendee_secondary_email=self.email.upper(), attendee_phone=self.phone)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertTrue(response.data["secondary_email_verified"])
                self.assertTrue(response.data["phone_verified"])
                self.assertEqual(response.data["attendee_secondary_email"], self.email)

    def test_invalid_contacts_and_primary_email_are_rejected(self):
        for fields in (
            {"attendee_secondary_email": "invalid-email"},
            {"attendee_secondary_email": "PRIMARY@example.com"},
            {"attendee_phone": "12345"},
        ):
            with self.subTest(fields=fields):
                response = self._post(self._event(allow_secondary_email=True, collect_phone=True), **fields)
                self.assertEqual(response.status_code, 400)

    def test_secondary_email_exceeding_storage_limit_is_a_validation_error(self):
        email = "a" * 64 + "@" + ".".join(["b" * 63, "c" * 63, "d" * 60]) + ".com"
        self.assertGreater(len(email), 254)
        response = self._post(self._event(allow_secondary_email=True), attendee_secondary_email=email)
        self.assertEqual(response.status_code, 400)
        self.assertIn("attendee_secondary_email", response.data)

    def test_client_verification_flags_cannot_establish_verified_contacts(self):
        event = self._event(allow_secondary_email=True, collect_phone=True)
        response = self._post(
            event,
            attendee_secondary_email=self.email,
            attendee_phone=self.phone,
            secondary_email_verified=True,
            phone_verified=True,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["secondary_email_verified"])
        self.assertFalse(response.data["phone_verified"])
        self.assertFalse(ContactEmail.objects.get(email_address=self.email).verified)
        self.assertFalse(ContactPhone.objects.get(phone_number=self.phone).verified)
