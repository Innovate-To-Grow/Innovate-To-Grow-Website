from django.core.management.base import BaseCommand

from apps.authn.models import EmailAuthChallenge
from apps.authn.services.members.registration_audit import find_register_reactivations, reactivation_reasons


class Command(BaseCommand):
    help = (
        "Read-only: list REGISTER codes issued to members that were already active, i.e. deactivated "
        "accounts that went through the old email-code self-reactivation path. Times are UTC."
    )

    def handle(self, *args, **options):
        rows = list(find_register_reactivations())
        for challenge in rows:
            member = challenge.member
            self.stdout.write(
                f"{challenge.status:9} code_sent={challenge.created_at:%Y-%m-%d %H:%M} "
                f"last_change={challenge.updated_at:%Y-%m-%d %H:%M} member={member.pk} "
                f"email={challenge.target_email} member_created={member.created_at:%Y-%m-%d} "
                f"active_now={member.is_active} | {', '.join(reactivation_reasons(challenge))}"
            )
        reactivated = sum(row.status == EmailAuthChallenge.Status.CONSUMED for row in rows)
        self.stdout.write(
            self.style.SUCCESS(f"{reactivated} reactivated account code(s), {len(rows)} flagged REGISTER code(s).")
        )
