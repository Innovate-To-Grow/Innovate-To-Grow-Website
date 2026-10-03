from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail, EmailAuthChallenge
from apps.authn.services.members.registration_audit import find_register_reactivations, reactivation_reasons

Member = get_user_model()
REGISTER = EmailAuthChallenge.Purpose.REGISTER
LOGIN = EmailAuthChallenge.Purpose.LOGIN
STATUS = EmailAuthChallenge.Status


class AuditRegisterReactivationsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.t0 = timezone.now() - timedelta(days=200)

    def _member(self, email, *, created_after=timedelta(0), is_active=True, last_login=None, **extra):
        member = Member.objects.create_user(is_active=is_active, **extra)
        ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
        Member.objects.filter(pk=member.pk).update(created_at=self.t0 + created_after, last_login=last_login)
        return member

    def _code(self, member, sent_after, *, purpose=REGISTER, status=STATUS.CONSUMED):
        sent = self.t0 + sent_after
        challenge = EmailAuthChallenge.objects.create(
            member=member,
            purpose=purpose,
            status=status,
            target_email=member.get_primary_email(),
            expires_at=sent + timedelta(minutes=10),
        )
        EmailAuthChallenge.objects.filter(pk=challenge.pk).update(created_at=sent, updated_at=sent)
        return challenge

    def _flagged(self) -> dict:
        return {row.pk: reactivation_reasons(row) for row in find_register_reactivations()}

    def test_genuine_signups_are_not_flagged(self):
        completed = self._member("completed@example.com")
        self._code(completed, timedelta(seconds=5))
        self._code(completed, timedelta(days=5), purpose=LOGIN)  # normal use after registering
        came_back_later = self._member("came-back@example.com")
        self._code(came_back_later, timedelta(seconds=5), status=STATUS.EXPIRED)
        self._code(came_back_later, timedelta(days=2))
        abandoned = self._member("abandoned@example.com", is_active=False)
        self._code(abandoned, timedelta(seconds=3), status=STATUS.PENDING)

        self.assertEqual(self._flagged(), {})

    def test_flags_codes_issued_to_already_active_members(self):
        self_registered = self._member("self-registered@example.com")
        self._code(self_registered, timedelta(seconds=5))
        self._code(self_registered, timedelta(days=10), purpose=LOGIN)
        reactivated = self._code(self_registered, timedelta(days=30))
        imported = self._member("imported@example.com")
        imported_code = self._code(imported, timedelta(days=60))
        attempt = self._member("attempt@example.com", is_active=False)
        attempt_code = self._code(attempt, timedelta(days=90), status=STATUS.PENDING)
        staff = self._member("staff@example.com", is_staff=True)
        staff_code = self._code(staff, timedelta(seconds=4))
        session_user = self._member("session@example.com", last_login=self.t0 + timedelta(days=3))
        self._code(session_user, timedelta(seconds=5))
        session_code = self._code(session_user, timedelta(days=20))

        self.assertEqual(
            self._flagged(),
            {
                reactivated.pk: ["earlier_other_code", "earlier_consumed_register"],
                imported_code.pk: ["not_created_by_signup"],
                attempt_code.pk: ["not_created_by_signup"],
                staff_code.pk: ["staff"],
                session_code.pk: ["earlier_consumed_register", "logged_in_before"],
            },
        )
        rows = list(find_register_reactivations())
        self.assertEqual(rows[-1].pk, attempt_code.pk)  # consumed rows sort before attempts
        self.assertEqual([row.status for row in rows[:-1]], [STATUS.CONSUMED] * 4)

    def test_command_prints_each_flagged_code_and_a_summary(self):
        imported = self._member("imported@example.com")
        self._code(imported, timedelta(days=60))
        attempt = self._member("attempt@example.com", is_active=False)
        self._code(attempt, timedelta(days=90), status=STATUS.PENDING)
        genuine = self._member("genuine@example.com")
        self._code(genuine, timedelta(seconds=5))
        out = StringIO()

        call_command("audit_register_reactivations", stdout=out)

        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("consumed "))
        self.assertIn(f"member={imported.pk} email=imported@example.com", lines[0])
        self.assertIn("active_now=True | not_created_by_signup", lines[0])
        self.assertTrue(lines[1].startswith("pending "))
        self.assertIn("email=attempt@example.com", lines[1])
        self.assertIn("active_now=False", lines[1])
        self.assertNotIn("genuine@example.com", out.getvalue())
        self.assertEqual(lines[2], "1 reactivated account code(s), 2 flagged REGISTER code(s).")

    def test_command_reports_nothing_found(self):
        out = StringIO()

        call_command("audit_register_reactivations", stdout=out)

        self.assertEqual(out.getvalue().strip(), "0 reactivated account code(s), 0 flagged REGISTER code(s).")
