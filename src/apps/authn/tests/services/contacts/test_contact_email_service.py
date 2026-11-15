from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail
from apps.authn.services.contacts.contact_emails import (
    _member_has_secondary,
    create_contact_email,
    delete_contact_email,
    make_contact_email_primary,
    resend_contact_email_verification,
    verify_contact_email_code,
)
from apps.authn.services.email.challenges import AuthChallengeInvalid
from apps.authn.services.security.key_encryption import decrypt_pem, encrypt_pem, is_encrypted
from apps.authn.tests.services.coverage.test_service_coverage import _member


class ContactEmailServiceTests(TestCase):
    def setUp(self):
        self.member = _member()

    def test_member_has_secondary_with_exclude(self):
        sec = ContactEmail.objects.create(member=self.member, email_address="sec@example.com", email_type="secondary")
        self.assertTrue(_member_has_secondary(self.member))
        self.assertFalse(_member_has_secondary(self.member, exclude_pk=sec.pk))

    def test_create_contact_email_rejects_second_secondary(self):
        ContactEmail.objects.create(member=self.member, email_address="sec1@example.com", email_type="secondary")
        with self.assertRaises(AuthChallengeInvalid):
            create_contact_email(member=self.member, email_address="sec2@example.com")

    @patch("apps.authn.services.contacts.contact_emails._notify_email_owner_in_background")
    def test_create_contact_email_conflict_notifies_owner(self, mock_notify):
        other = _member(email="taken@example.com", first_name="O", last_name="Wner")
        with self.assertRaises(AuthChallengeInvalid):
            create_contact_email(member=self.member, email_address="taken@example.com")
        mock_notify.assert_called_once()

    @patch("apps.authn.services.contacts.contact_emails.issue_email_challenge")
    @patch("apps.authn.services.contacts.contact_emails._notify_email_owner_in_background")
    def test_create_contact_email_integrity_error_notifies(self, mock_notify, mock_issue):
        with patch(
            "apps.authn.services.contacts.contact_emails.ContactEmail.objects.create",
            side_effect=IntegrityError("dup"),
        ):
            with self.assertRaises(AuthChallengeInvalid):
                create_contact_email(member=self.member, email_address="brandnew@example.com")
        mock_notify.assert_called_once()

    def test_verify_contact_email_code_not_found(self):
        import uuid

        with self.assertRaises(AuthChallengeInvalid):
            verify_contact_email_code(member=self.member, contact_email_id=uuid.uuid4(), code="123456")

    @patch("apps.authn.services.contacts.contact_emails.verify_email_code")
    def test_verify_contact_email_code_marks_contact_inside_approved_callback(self, mock_verify):
        contact = ContactEmail.objects.create(
            member=self.member,
            email_address="verify-me@example.com",
            email_type="secondary",
            verified=False,
        )

        def approve(**kwargs):
            return kwargs["approved_callback"](object())

        mock_verify.side_effect = approve
        result = verify_contact_email_code(member=self.member, contact_email_id=contact.pk, code="123456")

        self.assertEqual(result.pk, contact.pk)
        self.assertTrue(result.verified)
        self.assertTrue(callable(mock_verify.call_args.kwargs["approved_callback"]))

    def test_resend_verification_not_found(self):
        import uuid

        with self.assertRaises(AuthChallengeInvalid):
            resend_contact_email_verification(member=self.member, contact_email_id=uuid.uuid4())

    def test_resend_verification_already_verified(self):
        verified = ContactEmail.objects.create(
            member=self.member, email_address="ver@example.com", email_type="secondary", verified=True
        )
        with self.assertRaises(AuthChallengeInvalid):
            resend_contact_email_verification(member=self.member, contact_email_id=verified.pk)

    def test_delete_contact_email_not_found(self):
        import uuid

        with self.assertRaises(AuthChallengeInvalid):
            delete_contact_email(member=self.member, contact_email_id=uuid.uuid4())

    def test_make_primary_not_found(self):
        import uuid

        with self.assertRaises(AuthChallengeInvalid):
            make_contact_email_primary(member=self.member, contact_email_id=uuid.uuid4())

    @override_settings(FRONTEND_URL="https://example.com", BACKGROUND_JOBS_ENABLED=False)
    @patch(
        "apps.authn.services.contacts.contact_emails.start_in_process_task",
        side_effect=lambda target, *args, **_kwargs: target(*args),
    )
    @patch("apps.authn.services.email.send_email.send_notification_email")
    def test_notify_email_owner_logs_on_failure(self, mock_send, start_task):
        from apps.authn.services.contacts import contact_emails as svc

        mock_send.side_effect = RuntimeError("smtp down")
        svc._notify_email_owner_in_background("owner@example.com")
        mock_send.assert_called_once()
        start_task.assert_called_once()
        self.assertTrue(start_task.call_args.kwargs["best_effort_start"])

    @override_settings(FRONTEND_URL="https://example.com", BACKGROUND_JOBS_ENABLED=True)
    @patch("apps.authn.services.email.notification_jobs.enqueue_notification_email")
    def test_notify_email_owner_uses_durable_queue_when_enabled(self, mock_enqueue):
        from apps.authn.services.contacts import contact_emails as svc

        svc._notify_email_owner_in_background("owner@example.com")

        mock_enqueue.assert_called_once_with(
            recipient="owner@example.com",
            subject="Security notice - Innovate to Grow",
            template="authn/email/email_claim_notification.html",
            context={"account_url": "https://example.com/account"},
        )


class KeyEncryptionTests(TestCase):
    def test_round_trip(self):
        encrypted = encrypt_pem("PEM-DATA")
        self.assertTrue(is_encrypted(encrypted))
        self.assertEqual(decrypt_pem(encrypted), "PEM-DATA")

    def test_legacy_plaintext_passthrough(self):
        self.assertEqual(decrypt_pem("plain-pem"), "plain-pem")
        self.assertFalse(is_encrypted("plain-pem"))

    @override_settings(SECRET_KEY="a-different-secret-key-entirely")
    def test_decrypt_with_wrong_key_raises(self):
        # Encrypt with current key, then change the key so decryption fails.
        with override_settings(SECRET_KEY="original-secret"):
            encrypted = encrypt_pem("PEM-DATA")
        with self.assertRaisesMessage(ValueError, "Failed to decrypt private key"):
            decrypt_pem(encrypted)
