from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.cli_admin.models import CliAccessToken, CliAuthorizationCode


class Command(BaseCommand):
    help = "Delete expired CLI authorization codes and expired/revoked CLI access tokens."

    def handle(self, *args, **options):
        now = timezone.now()
        codes_deleted, _ = CliAuthorizationCode.objects.filter(expires_at__lte=now).delete()
        tokens_deleted, _ = CliAccessToken.objects.filter(Q(expires_at__lte=now) | Q(revoked_at__isnull=False)).delete()
        self.stdout.write(
            self.style.SUCCESS(f"Removed {codes_deleted} authorization code(s) and {tokens_deleted} access token(s).")
        )
