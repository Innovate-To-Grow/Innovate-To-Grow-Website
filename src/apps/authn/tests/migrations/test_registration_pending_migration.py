"""0021 backfill: only unfinished self-service signups become ``registration_pending``."""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, EmailAuthChallenge

mark_pending_registrations = importlib.import_module(
    "apps.authn.migrations.0021_member_registration_pending"
).mark_pending_registrations

Member = get_user_model()
PURPOSE = EmailAuthChallenge.Purpose
STATUS = EmailAuthChallenge.Status


class MarkPendingRegistrationsTests(TestCase):
    def _member(self, email, *, is_active=False, verified=False, **extra):
        member = Member.objects.create_user(is_active=is_active, **extra)
        ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=verified)
        return member

    @staticmethod
    def _challenge(member, purpose=PURPOSE.REGISTER, status=STATUS.PENDING):
        return EmailAuthChallenge.objects.create(
            member=member,
            purpose=purpose,
            status=status,
            target_email=member.get_primary_email(),
            expires_at=EmailAuthChallenge.default_expiry(),
        )

    def _run(self):
        mark_pending_registrations(django_apps, None)

    def _pending(self, member) -> bool:
        member.refresh_from_db()
        return member.registration_pending

    def test_abandoned_signups_are_flagged(self):
        email_code_signup = self._member("abandoned@example.com")
        self._challenge(email_code_signup)
        password_signup = self._member("password@example.com", password="StrongPass123!", first_name="Pat")
        self._challenge(password_signup, status=STATUS.EXPIRED)
        self._challenge(password_signup)

        self._run()

        self.assertTrue(self._pending(email_code_signup))
        self.assertTrue(self._pending(password_signup))

    def test_deactivated_and_other_inactive_members_stay_unflagged(self):
        # Self-registered then deactivated: verified email + consumed REGISTER challenge.
        completed = self._member("completed@example.com", verified=True)
        self._challenge(completed, status=STATUS.CONSUMED)
        # Consumed challenge alone (email later un-verified) still proves it was activated.
        consumed_only = self._member("consumed-only@example.com")
        self._challenge(consumed_only, status=STATUS.CONSUMED)
        # Imported / admin-created then deactivated: unverified email, never went through signup.
        imported = self._member("imported@example.com")
        # Has a verified phone, so it was in use at some point.
        phone_user = self._member("phone@example.com")
        self._challenge(phone_user)
        ContactPhone.objects.create(member=phone_user, phone_number="2095550100", verified=True)
        # Inactive staff and members that once logged in are never self-service signups.
        staff = self._member("staff@example.com", is_staff=True)
        self._challenge(staff)
        logged_in = self._member("logged-in@example.com")
        Member.objects.filter(pk=logged_in.pk).update(last_login=logged_in.date_joined)
        self._challenge(logged_in)
        # Active members are not pending.
        active = self._member("active@example.com", is_active=True)
        self._challenge(active)

        self._run()

        for member in (completed, consumed_only, imported, phone_user, staff, logged_in, active):
            with self.subTest(email=member.get_primary_email()):
                self.assertFalse(self._pending(member))
