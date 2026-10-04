from django.core.management.base import BaseCommand, CommandError

from apps.authn.services.send_verification import cleanup_expired_records
from apps.authn.services.send_verification.cleanup import DEFAULT_BATCH_SIZE


class Command(BaseCommand):
    help = (
        "Expire pending send-verification challenges and delete records past the retention window, in bounded "
        "batches. The background worker also runs this hourly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Primary keys per UPDATE/DELETE batch (default {DEFAULT_BATCH_SIZE}).",
        )

    def handle(self, *args, **options):
        batch_size = options.get("batch_size", DEFAULT_BATCH_SIZE)
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")
        result = cleanup_expired_records(batch_size=batch_size)
        self.stdout.write(
            self.style.SUCCESS(
                "Expired {expired_challenges} challenges; deleted {deleted_challenges} challenges "
                "and {deleted_requests} send requests.".format(**result)
            )
        )
