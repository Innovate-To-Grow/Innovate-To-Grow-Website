import uuid
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone, EmailAuthChallenge
from apps.event.models import EventRegistration
from apps.event.tests.helpers import make_member
from apps.event.tests.views.registration.contacts.test_registration_contacts import _RegistrationContactPolicyCase


class RegistrationContactPolicyTest(_RegistrationContactPolicyCase):
    def test_successful_email_proof_is_consumed_and_synced_only_after_registration(self):
        event = self._event(allow_secondary_email=True, verify_secondary_email=True)
        proof = self._email_proof(event)
        self.assertFalse(ContactEmail.objects.filter(email_address=self.email).exists())
        response = self._post(event, **self._proof_data(proof))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["secondary_email_verified"])
        self.assertNotIn("secondary_email_verification_token", response.data)
        proof.refresh_from_db()
        self.assertEqual(proof.status, EmailAuthChallenge.Status.CONSUMED)
        self.assertTrue(ContactEmail.objects.get(member=self.member, email_address=self.email).verified)

    def test_email_proof_upgrades_own_unverified_contact(self):
        contact = ContactEmail.objects.create(member=self.member, email_address=self.email, email_type="secondary")
        event = self._event(allow_secondary_email=True, verify_secondary_email=True)
        proof = self._email_proof(event)
        self.assertEqual(self._post(event, **self._proof_data(proof)).status_code, 201)
        contact.refresh_from_db()
        self.assertTrue(contact.verified)

    def test_other_members_verified_contacts_do_not_bypass_verification(self):
        other = make_member(email="other@example.com")
        ContactEmail.objects.create(member=other, email_address=self.email, email_type="secondary", verified=True)
        ContactPhone.objects.create(member=other, phone_number=self.phone, region="1-US", verified=True)
        for fields in ({"attendee_secondary_email": self.email}, {"attendee_phone": self.phone}):
            with self.subTest(fields=fields):
                event = self._event(
                    allow_secondary_email=True, verify_secondary_email=True, collect_phone=True, verify_phone=True
                )
                self.assertEqual(self._post(event, **fields).status_code, 400)

    def test_email_verification_never_reassigns_another_members_contact(self):
        other = make_member(email="other@example.com")
        contact = ContactEmail.objects.create(member=other, email_address=self.email, email_type="secondary")
        event = self._event(allow_secondary_email=True, verify_secondary_email=True)
        proof = self._email_proof(event)
        response = self._post(event, **self._proof_data(proof))
        self.assertEqual(response.status_code, 201)
        contact.refresh_from_db()
        self.assertEqual(contact.member_id, other.pk)
        self.assertFalse(contact.verified)

    def test_mismatched_expired_unverified_and_consumed_email_proofs_are_rejected(self):
        other = make_member(email="other@example.com")
        for overrides in (
            {"member": other},
            {"target_email": "wrong@example.com"},
            {"context_identifier": f"event-registration:{uuid.uuid4()}"},
            {"purpose": EmailAuthChallenge.Purpose.PASSWORD_RESET},
            {"expires_at": timezone.now() - timedelta(seconds=1)},
            {"status": EmailAuthChallenge.Status.CONSUMED},
            {"status": EmailAuthChallenge.Status.PENDING},
        ):
            with self.subTest(overrides=overrides):
                event = self._event(allow_secondary_email=True, verify_secondary_email=True)
                proof = self._email_proof(event, **overrides)
                response = self._post(event, **self._proof_data(proof))
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["code"], "secondary_email_verification_required")
                self.assertFalse(EventRegistration.objects.filter(event=event).exists())
        self.assertFalse(ContactEmail.objects.filter(email_address=self.email).exists())

    def test_wrong_token_or_challenge_id_is_rejected(self):
        for field, value in (
            ("secondary_email_verification_token", "incorrect-token"),
            ("secondary_email_verification_challenge_id", str(uuid.uuid4())),
        ):
            with self.subTest(field=field):
                event = self._event(allow_secondary_email=True, verify_secondary_email=True)
                proof = self._email_proof(event)
                self.assertEqual(self._post(event, **self._proof_data(proof, **{field: value})).status_code, 400)
                proof.refresh_from_db()
                self.assertEqual(proof.status, EmailAuthChallenge.Status.VERIFIED)

    def test_other_contact_failure_rolls_back_email_proof_consumption(self):
        event = self._event(
            allow_secondary_email=True, verify_secondary_email=True, collect_phone=True, require_phone=True
        )
        proof = self._email_proof(event)
        self.assertEqual(self._post(event, **self._proof_data(proof)).status_code, 400)
        proof.refresh_from_db()
        self.assertEqual(proof.status, EmailAuthChallenge.Status.VERIFIED)
        self.assertFalse(ContactEmail.objects.filter(email_address=self.email).exists())

    def test_registration_failure_rolls_back_email_proof_and_account_updates(self):
        event = self._event(allow_secondary_email=True, verify_secondary_email=True)
        proof = self._email_proof(event)
        self.client.raise_request_exception = False
        with patch(
            "apps.event.views.registration.create.send_initial_ticket_email", side_effect=RuntimeError("test failure")
        ):
            response = self._post(event, **self._proof_data(proof))
        self.assertEqual(response.status_code, 500)
        proof.refresh_from_db()
        self.assertEqual(proof.status, EmailAuthChallenge.Status.VERIFIED)
        self.assertFalse(EventRegistration.objects.filter(event=event).exists())
        self.assertFalse(ContactEmail.objects.filter(email_address=self.email).exists())
