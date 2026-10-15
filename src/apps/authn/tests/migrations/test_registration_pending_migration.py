"""Historical inactive members must never gain self-activation during migration."""

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RegistrationPendingMigrationTests(TransactionTestCase):
    migrate_from = [("authn", "0021_login_failure_window")]
    migrate_to = [("authn", "0022_member_registration_pending")]

    def test_old_register_code_cannot_identify_safe_pending_member(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldMember = old_apps.get_model("authn", "Member")
        OldContactEmail = old_apps.get_model("authn", "ContactEmail")
        OldChallenge = old_apps.get_model("authn", "EmailAuthChallenge")

        def make_old_signup(email):
            member = OldMember.objects.create(is_active=False)
            OldContactEmail.objects.create(member=member, email_address=email, verified=False)
            OldChallenge.objects.create(
                member=member,
                purpose="register",
                status="pending",
                target_email=email,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            return member

        # These accounts have the same durable data at migration time. One was
        # once activated by an administrator and later deactivated; the other
        # is an unfinished signup. Neither may be trusted to self-activate.
        deactivated = make_old_signup("deactivated@example.com")
        OldMember.objects.filter(pk=deactivated.pk).update(is_active=True)
        OldMember.objects.filter(pk=deactivated.pk).update(is_active=False)
        unfinished = make_old_signup("unfinished@example.com")

        MigrationExecutor(connection).migrate(self.migrate_to)
        NewMember = (
            MigrationExecutor(connection).loader.project_state(self.migrate_to).apps.get_model("authn", "Member")
        )
        self.assertFalse(NewMember.objects.get(pk=deactivated.pk).registration_pending)
        self.assertFalse(NewMember.objects.get(pk=unfinished.pk).registration_pending)
