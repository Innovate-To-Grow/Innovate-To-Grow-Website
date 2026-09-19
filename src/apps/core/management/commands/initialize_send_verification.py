"""Initialize the required send-verification signing key without changing policy."""

import secrets

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.core.models import SendVerificationConfig

# Serialize first-row creation as well as repairs when several production
# replicas start together. Row locks alone cannot protect an empty table.
_INITIALIZATION_LOCK_ID = 0x69326773656E64


class Command(BaseCommand):
    help = "Initialize a missing send-verification signing key without rotating keys or changing policy."

    def handle(self, *args, **options):
        if getattr(settings, "SEND_VERIFICATION_HMAC_SECRET", None) is not None:
            self.stdout.write("Explicit send-verification signing-key override; database initialization skipped.")
            return

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_INITIALIZATION_LOCK_ID])

            config = SendVerificationConfig.objects.select_for_update().filter(is_active=True).first()
            if config is None:
                if SendVerificationConfig.objects.exists():
                    self.stdout.write("Inactive send-verification configurations exist; activation left unchanged.")
                    return
                SendVerificationConfig.objects.create(
                    name="Production",
                    is_active=True,
                    mode=SendVerificationConfig.Mode.OBSERVE,
                    hmac_secret=secrets.token_urlsafe(48),
                )
                message = "Initialized active SendVerificationConfig with a secure signing key in observe mode."
            elif config.hmac_secret.strip():
                self.stdout.write("Active send-verification signing key already exists; configuration unchanged.")
                return
            else:
                config.hmac_secret = secrets.token_urlsafe(48)
                config.save(update_fields=["hmac_secret", "updated_at"])
                message = "Initialized missing active send-verification signing key; existing policy preserved."

        self.stdout.write(self.style.SUCCESS(message))
